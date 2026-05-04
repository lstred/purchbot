from __future__ import annotations

from datetime import date
import re
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

from . import queries
from .db import read_dataframe


def _expand_in_clause(column: str, values: Iterable[str], prefix: str) -> Tuple[str, Dict[str, str]]:
    values = list(values)
    if not values:
        return "1 = 1", {}

    params = {f"{prefix}_{idx}": value for idx, value in enumerate(values)}
    placeholders = ", ".join(f":{key}" for key in params)
    clause = f"{column} IN ({placeholders})"
    return clause, params


def _append_filter(sql: str, clause: str) -> str:
    if "WHERE" in sql.upper():
        return f"{sql}\n  AND {clause}"
    return f"{sql}\nWHERE {clause}"


def _format_date_bounds(column: str, start: Optional[date], end: Optional[date]) -> Tuple[str, Dict[str, str]]:
    param_base = re.sub(r'[^0-9a-zA-Z_]', '_', column)
    clauses = []
    params: Dict[str, str] = {}
    if start:
        clauses.append(f"{column} >= :{param_base}_start")
        params[f"{param_base}_start"] = start.isoformat()
    if end:
        clauses.append(f"{column} <= :{param_base}_end")
        params[f"{param_base}_end"] = end.isoformat()
    return " AND ".join(clauses), params


def _normalise_dates(df: pd.DataFrame, columns: List[str]) -> None:
    for col in columns:
        if col in df.columns:
            # Handle YYYYMMDD format explicitly
            df[col] = pd.to_datetime(df[col], format="%Y%m%d", errors="coerce")


def load_orders(
    connection_string: str,
    cost_centers: Optional[Iterable[str]] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> pd.DataFrame:
    sql = queries.ORDERS_BASE
    params: Dict[str, str] = {}

    if cost_centers:
        clause, clause_params = _expand_in_clause("i.[ICCTR]", cost_centers, "cc")
        sql = _append_filter(sql, clause)
        params.update(clause_params)

    if start_date or end_date:
        # Include rows when EITHER the order entry date OR ship date OR invoice ship date
        # is within the selected window. This ensures shipped sales count even if entered earlier,
        # while still capturing unshipped backorders via entry date.
        entry_clause, entry_params = _format_date_bounds(
            "CONVERT(date, CONVERT(varchar(8), o.[ORDER_ENTRY_DATE_YYYYMMDD]), 112)",
            start_date,
            end_date,
        )
        ship_clause, ship_params = _format_date_bounds(
            "CONVERT(date, o.[ORDER_SHIP_DATE])",
            start_date,
            end_date,
        )
        inv_clause, inv_params = _format_date_bounds(
            "CONVERT(date, o.[INVOICE_SHIP_DATE])",
            start_date,
            end_date,
        )
        sub_clauses = []
        if entry_clause:
            sub_clauses.append(f"({entry_clause})")
        if ship_clause:
            sub_clauses.append(f"({ship_clause})")
        if inv_clause:
            sub_clauses.append(f"({inv_clause})")
        if sub_clauses:
            sql = _append_filter(sql, "(" + " OR ".join(sub_clauses) + ")")
            params.update(entry_params)
            params.update(ship_params)
            params.update(inv_params)

    df = read_dataframe(connection_string, sql, params=params or None)
    if df.empty:
        # Ensure required columns exist to prevent KeyErrors downstream
        return pd.DataFrame(columns=[
            "order_entry_date",  # used for filtering/sorting even when empty
            "sku",               # required for groupby operations downstream
        ])

    _normalise_dates(df, ["order_ship_date", "invoice_ship_date"])
    df["order_entry_date"] = pd.to_datetime(
        df.get("order_entry_date_raw"), format="%Y%m%d", errors="coerce"
    )
    # ORDER_DATE is a standard SQL date column (YYYY-MM-DD), not the YYYYMMDD numeric format
    if "order_date" in df.columns:
        df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
    # Normalize SKU identifiers for consistent joins and filtering
    if "sku" in df.columns:
        df["sku"] = df["sku"].astype(str).str.strip()
    return df


def load_purchase_orders(
    connection_string: str,
    cost_centers: Optional[Iterable[str]] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> pd.DataFrame:
    sql = queries.PURCHASE_ORDERS
    params: Dict[str, str] = {}

    if cost_centers:
        clause, clause_params = _expand_in_clause("i.[ICCTR]", cost_centers, "po_cc")
        sql = _append_filter(sql, clause)
        params.update(clause_params)

    if start_date or end_date:
        # Include rows with ETA in range OR with NULL ETA (to catch missing/delayed ETAs)
        eta_clauses = []
        if start_date:
            eta_clauses.append("o.[PO_ETA_DATE] >= :po_eta_start")
            params["po_eta_start"] = start_date.isoformat()
        if end_date:
            eta_clauses.append("o.[PO_ETA_DATE] <= :po_eta_end")
            params["po_eta_end"] = end_date.isoformat()
        if eta_clauses:
            eta_clause = " AND ".join(eta_clauses)
            sql = _append_filter(sql, f"(({eta_clause}) OR o.[PO_ETA_DATE] IS NULL)")

    df = read_dataframe(connection_string, sql, params=params or None)
    if df.empty:
        return df

    _normalise_dates(df, ["eta_date"])
    df["order_entry_date"] = pd.to_datetime(
        df.get("order_entry_date_raw"), format="%Y%m%d", errors="coerce"
    )
    # Normalize SKU identifiers
    if "sku" in df.columns:
        df["sku"] = df["sku"].astype(str).str.strip()
    return df


def load_open_orders(
    connection_string: str,
    cost_centers: Optional[Iterable[str]] = None,
    order_date: Optional[date] = None,
) -> pd.DataFrame:
    """Load Open Orders with required columns for the Open Orders UI.

    Filters:
      - cost_centers: limits by ITEM.ICCTR values
      - order_date: filters by ORDER_ENTRY_DATE (exact date match)
    """
    sql = queries.OPEN_ORDERS_LIST
    params: Dict[str, str] = {}

    if cost_centers:
        clause, clause_params = _expand_in_clause("i.[ICCTR]", cost_centers, "oo_cc")
        sql = _append_filter(sql, clause)
        params.update(clause_params)

    if order_date:
        # _ORDERS stores entry as yyyymmdd numeric/text; convert to date and match exactly
        sql = _append_filter(
            sql,
            "CONVERT(date, CONVERT(varchar(8), o.[ORDER_ENTRY_DATE_YYYYMMDD]), 112) = :order_date",
        )
        params["order_date"] = order_date.isoformat()

    df = read_dataframe(connection_string, sql, params=params or None)
    if df.empty:
        return df

    # Normalize/convert types
    _normalise_dates(df, ["order_ship_date"])  # may contain nulls
    df["order_entry_date"] = pd.to_datetime(
        df.get("order_entry_date_raw"), format="%Y%m%d", errors="coerce"
    )
    # Numeric coercions for money/qty
    for col in [
        "line_gpp_with_funds",
        "quantity_ordered",
        "price_per_um",
        "cost_per_um",
        "extended_price_no_funds",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Normalize text fields
    for col in [
        "order_reference",
        "item_mfgr_color_pat",
        "item_desc_1",
        "unit_of_measure",
        "bank_name2",
        "salesperson_desc",
        "detail_line_status",
        "cost_center",
    ]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    # Normalize status to uppercase for reliable comparisons
    if "detail_line_status" in df.columns:
        df["detail_line_status"] = df["detail_line_status"].str.upper()

    # Apply robust Supplier 001 filter and exclude account 1 at the DataFrame level
    # Normalize supplier_number: numeric-like -> zero-padded 3-digit string; else trimmed string
    try:
        supp_raw = df.get("supplier_number")
        if supp_raw is not None:
            s = supp_raw.astype(str).str.strip()
            num = pd.to_numeric(s, errors="coerce")
            norm = s.copy()
            mask_num = num.notna()
            norm.loc[mask_num] = num.loc[mask_num].astype("Int64").astype(str).str.zfill(3)
            df = df.loc[norm == "001"].copy()
    except Exception:
        # Best effort; if supplier not present, leave as-is
        pass
    # Exclude account number 1
    try:
        acct_num = pd.to_numeric(df.get("account_number"), errors="coerce")
        df = df.loc[~(acct_num == 1)].copy()
    except Exception:
        pass

    return df


def load_items(connection_string: str, cost_centers: Optional[Iterable[str]] = None) -> pd.DataFrame:
    sql = queries.ITEMS
    params: Dict[str, str] = {}

    if cost_centers:
        clause, clause_params = _expand_in_clause("[ICCTR]", cost_centers, "item_cc")
        sql = _append_filter(sql, clause)
        params.update(clause_params)

    df = read_dataframe(connection_string, sql, params=params or None)
    if df.empty:
        return df

    # Normalize SKU identifiers
    if "sku" in df.columns:
        df["sku"] = df["sku"].astype(str).str.strip()
    df["item_lead_time_days"] = pd.to_numeric(df.get("item_lead_time_days"), errors="coerce")
    df["item_width_inches"] = pd.to_numeric(df.get("item_width_inches"), errors="coerce")
    # Normalize iixref to string for filtering (non-empty means exclude from Stock Turn)
    if "iixref" in df.columns:
        df["iixref"] = df["iixref"].fillna("").astype(str)
    if "supplier_number" in df.columns:
        df["supplier_number"] = df["supplier_number"].fillna("").astype(str).str.strip()
    # Normalize description to string and strip
    if "sku_description" in df.columns:
        df["sku_description"] = df["sku_description"].apply(lambda v: v.strip() if isinstance(v, str) else v)
    # Normalize item pattern (IPATT) for grouping
    if "item_pattern" in df.columns:
        df["item_pattern"] = df["item_pattern"].fillna("").astype(str).str.strip()
    return df


def load_items_all(connection_string: str, cost_centers: Optional[Iterable[str]] = None) -> pd.DataFrame:
    """Load all items (including non-inventory) for Price List Generator/exports.
    Mirrors load_items normalization but without the IINVEN='Y' filter, but excludes
    discontinued items by requiring ITEM.IDISCD = 0.
    """
    sql = queries.ITEMS_ALL
    params: Dict[str, str] = {}

    if cost_centers:
        clause, clause_params = _expand_in_clause("[ICCTR]", cost_centers, "item_cc_all")
        sql = _append_filter(sql, clause)
        params.update(clause_params)

    df = read_dataframe(connection_string, sql, params=params or None)
    if df.empty:
        return df

    # Normalize SKU identifiers
    if "sku" in df.columns:
        df["sku"] = df["sku"].astype(str).str.strip()
    df["item_lead_time_days"] = pd.to_numeric(df.get("item_lead_time_days"), errors="coerce")
    df["item_width_inches"] = pd.to_numeric(df.get("item_width_inches"), errors="coerce")
    if "iixref" in df.columns:
        df["iixref"] = df["iixref"].fillna("").astype(str)
    if "supplier_number" in df.columns:
        df["supplier_number"] = df["supplier_number"].fillna("").astype(str).str.strip()
    if "sku_description" in df.columns:
        df["sku_description"] = df["sku_description"].apply(lambda v: v.strip() if isinstance(v, str) else v)
    if "item_pattern" in df.columns:
        df["item_pattern"] = df["item_pattern"].fillna("").astype(str).str.strip()
    if "inventory_flag" in df.columns:
        df["inventory_flag"] = df["inventory_flag"].fillna("").astype(str).str.strip()
    if "discontinued_flag" in df.columns:
        # Normalise as integer 0/1 when present
        df["discontinued_flag"] = pd.to_numeric(df.get("discontinued_flag"), errors="coerce").fillna(0).astype(int)
    return df


def load_suppliers(connection_string: str, cost_centers: Optional[Iterable[str]] = None) -> List[str]:
    """Return distinct supplier_numbers for relevant items (filtered by cost centers when provided)."""
    items = load_items(connection_string, cost_centers)
    if items.empty or "supplier_number" not in items.columns:
        return []
    suppliers = items["supplier_number"].dropna().astype(str)
    suppliers = suppliers[suppliers.str.len() > 0]
    return sorted(suppliers.unique().tolist())


def load_price_classes(connection_string: str) -> pd.DataFrame:
    return read_dataframe(connection_string, queries.PRICE_CLASSES)


def load_product_lines(connection_string: str) -> pd.DataFrame:
    df = read_dataframe(connection_string, queries.PRODUCT_LINES)
    if df.empty:
        return df
    df["product_line_lead_time_days"] = pd.to_numeric(df.get("product_line_lead_time_days"), errors="coerce")
    return df


def load_rolls(connection_string: str, cost_centers: Optional[Iterable[str]] = None) -> pd.DataFrame:
    sql = queries.ROLLS
    params: Dict[str, str] = {}

    if cost_centers:
        clause, clause_params = _expand_in_clause("i.[ICCTR]", cost_centers, "roll_cc")
        sql = _append_filter(
            sql,
            f"[ItemNumber] IN (SELECT i.[ItemNumber] FROM dbo.ITEM AS i WHERE i.[IINVEN] = 'Y' AND {clause})",
        )
        params.update(clause_params)

    df = read_dataframe(connection_string, sql, params=params or None)
    if df.empty:
        return df

    df["available_quantity"] = pd.to_numeric(df.get("available_quantity"), errors="coerce").fillna(0)
    if "receive_date" in df.columns:
        _normalise_dates(df, ["receive_date"])
    # Normalize SKU identifiers
    if "sku" in df.columns:
        df["sku"] = df["sku"].astype(str).str.strip()
    return df


def load_open_receipts(connection_string: str) -> pd.DataFrame:
    df = read_dataframe(connection_string, queries.OPEN_RECEIPTS)
    if df.empty:
        return df

    _normalise_dates(df, ["receipt_date"])
    df["quantity_received"] = pd.to_numeric(df.get("quantity_received"), errors="coerce").fillna(0)
    df["sku"] = (
        df.get("mfgr_part", "").fillna("")
        + df.get("color_part", "").fillna("")
        + df.get("pattern_part", "").fillna("")
    ).astype(str).str.strip()
    return df


def load_cost_centers(connection_string: str) -> List[str]:
    df = read_dataframe(connection_string, queries.COST_CENTERS)
    if df.empty or "cost_center" not in df.columns:
        return []
    centers = df["cost_center"].dropna().astype(str).tolist()
    # Exclude any cost centers that start with '1'
    centers = [cc for cc in centers if not cc.strip().startswith("1")]
    return sorted(centers)


def load_itemstks(connection_string: str) -> pd.DataFrame:
    df = read_dataframe(connection_string, queries.ITEMSTK)
    if df.empty:
        return df
    # Normalize and aggregate: take the maximum JSTOCK per SKU when multiple rows exist
    if "sku" in df.columns:
        df["sku"] = df["sku"].astype(str).str.strip()
    df["jstock"] = pd.to_numeric(df.get("jstock"), errors="coerce").fillna(0.0)
    df = df[[c for c in ["sku", "jstock"] if c in df.columns]].copy()
    if not df.empty:
        df = df.groupby("sku", as_index=False)["jstock"].max()
    return df


def load_openpo_partials(connection_string: str) -> pd.DataFrame:
    """Return partially received PO quantities per SKU from OPENPO_D.

    Criteria:
      - D@ACCT = 1
      - D@DEL8 <> '#'
      - D@QTYP > 0
    Computation per SKU:
      sum(D@QTYO) - sum(D@QTYP)
    """
    df = read_dataframe(connection_string, queries.OPENPO_D_PARTIALS)
    if df.empty:
        return df

    # Build SKU as D@MFGR + D@COLO + D@PATT
    for col in ["mfgr", "colo", "patt"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()
        else:
            df[col] = ""
    df["sku"] = (df["mfgr"] + df["colo"] + df["patt"]).astype(str)

    # Coerce numerics
    df["qty_ordered"] = pd.to_numeric(df.get("qty_ordered"), errors="coerce").fillna(0.0)
    df["qty_posted"] = pd.to_numeric(df.get("qty_posted"), errors="coerce").fillna(0.0)

    agg = df.groupby("sku", as_index=False).agg(qty_ordered_total=("qty_ordered", "sum"), qty_posted_total=("qty_posted", "sum"))
    agg["partial_received_po"] = (agg["qty_ordered_total"] - agg["qty_posted_total"]).astype(float)
    # Keep only positive partials
    agg = agg[agg["partial_received_po"] > 0]
    return agg[["sku", "partial_received_po"]]


def load_openpo_pending(connection_string: str) -> pd.DataFrame:
        """Return pending PO quantity per SKU from OPENPO_D.

        Criteria:
            - D@ACCT = 1
            - D@DEL8 <> '#'
            - D@SUPPP <> '001' (supplier filter)
        Computation per SKU:
            sum(D@QTYO) - sum(D@QTYP)
        """
        df = read_dataframe(connection_string, queries.OPENPO_D_PENDING)
        if df.empty:
                return df

        # Build SKU as D@MFGR + D@COLO + D@PATT
        for col in ["mfgr", "colo", "patt"]:
                if col in df.columns:
                        df[col] = df[col].fillna("").astype(str).str.strip()
                else:
                        df[col] = ""
        df["sku"] = (df["mfgr"] + df["colo"] + df["patt"]).astype(str)

        # Coerce numerics
        df["qty_ordered"] = pd.to_numeric(df.get("qty_ordered"), errors="coerce").fillna(0.0)
        df["qty_posted"] = pd.to_numeric(df.get("qty_posted"), errors="coerce").fillna(0.0)

        agg = df.groupby("sku", as_index=False).agg(qty_ordered_total=("qty_ordered", "sum"), qty_posted_total=("qty_posted", "sum"))
        agg["po_pending_qty"] = (agg["qty_ordered_total"] - agg["qty_posted_total"]).astype(float)
        # Keep only positive pendings
        agg = agg[agg["po_pending_qty"] > 0]
        return agg[["sku", "po_pending_qty"]]

def load_openpo_m_restock_fees(connection_string: str) -> pd.DataFrame:
    """Load restocking fee lines from OPENPO_M (GL 9140)."""
    sql = queries.OPENPO_M_RESTOCK_FEES
    df = read_dataframe(connection_string, sql)
    if df.empty:
        return df
    # Normalize numeric fields for joins and math
    df = df.copy()
    df["order_number"] = pd.to_numeric(df.get("order_number"), errors="coerce")
    df["line_number"] = pd.to_numeric(df.get("line_number"), errors="coerce")
    df["gl_number"] = pd.to_numeric(df.get("gl_number"), errors="coerce")
    df["fee_amount"] = pd.to_numeric(df.get("fee_amount"), errors="coerce")
    return df


def load_openpo_m_lines(connection_string: str) -> pd.DataFrame:
    """Load OPENPO_M lines including message text (M@MSG)."""
    sql = queries.OPENPO_M_LINES
    df = read_dataframe(connection_string, sql)
    if df.empty:
        return df
    df = df.copy()
    df["order_number"] = pd.to_numeric(df.get("order_number"), errors="coerce")
    df["line_number"] = pd.to_numeric(df.get("line_number"), errors="coerce")
    df["gl_number"] = pd.to_numeric(df.get("gl_number"), errors="coerce")
    df["fee_amount"] = pd.to_numeric(df.get("fee_amount"), errors="coerce")
    if "message_text" in df.columns:
        df["message_text"] = df["message_text"].fillna("").astype(str).str.strip()
    else:
        df["message_text"] = ""
    return df


def load_dropped_items(
    connection_string: str,
    cost_centers: Optional[Iterable[str]] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> pd.DataFrame:
    """Load dropped items - items with DI in IPOL1, IPOL2, or IPOL3 fields.
    
    Filters:
      - cost_centers: limits by ITEM.ICCTR values
      - start_date/end_date: filters by discontinued date (IDISCD converted from mmddyy)
    """
    sql = queries.DROPPED_ITEMS
    params: Dict[str, str] = {}

    if cost_centers:
        clause, clause_params = _expand_in_clause("[ICCTR]", cost_centers, "drop_cc")
        sql = _append_filter(sql, clause)
        params.update(clause_params)

    df = read_dataframe(connection_string, sql, params=params or None)
    if df.empty:
        return df

    # Parse IDISCD from mmddyy numeric format to actual date
    # e.g., 123124 = 12/31/24 (December 31, 2024)
    def parse_mmddyy(val):
        try:
            s = str(int(float(val))).zfill(6)  # Ensure 6 digits
            mm = int(s[0:2])
            dd = int(s[2:4])
            yy = int(s[4:6])
            # Assume 20xx for years 00-99
            yyyy = 2000 + yy
            return date(yyyy, mm, dd)
        except Exception:
            return None

    if "discontinued_date_raw" in df.columns:
        df["discontinued_date"] = df["discontinued_date_raw"].apply(parse_mmddyy)
    else:
        df["discontinued_date"] = None

    # Filter by date range if provided
    if start_date:
        df = df[df["discontinued_date"] >= start_date]
    if end_date:
        df = df[df["discontinued_date"] <= end_date]

    # Normalize SKU identifiers
    if "sku" in df.columns:
        df["sku"] = df["sku"].astype(str).str.strip()
    if "sku_description" in df.columns:
        df["sku_description"] = df["sku_description"].apply(lambda v: v.strip() if isinstance(v, str) else v)
    if "manufacturer" in df.columns:
        df["manufacturer"] = df["manufacturer"].fillna("").astype(str).str.strip()
    if "supplier_number" in df.columns:
        df["supplier_number"] = df["supplier_number"].fillna("").astype(str).str.strip()

    return df


def load_supplier_performance(
    connection_string: str,
    cost_centers: Optional[Iterable[str]] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> pd.DataFrame:
    """Load supplier performance data - sales by supplier over time.
    
    Filters:
      - cost_centers: limits by ITEM.ICCTR values
      - start_date/end_date: filters by invoice date
    """
    sql = queries.SUPPLIER_PERFORMANCE
    params: Dict[str, str] = {}

    if cost_centers:
        clause, clause_params = _expand_in_clause("i.[ICCTR]", cost_centers, "supp_perf_cc")
        sql = _append_filter(sql, clause)
        params.update(clause_params)

    df = read_dataframe(connection_string, sql, params=params or None)
    if df.empty:
        return df

    # Parse date fields - invoice_date_raw is YYYYMMDD format (e.g., 20250811)
    # Handle various formats: numeric, string with/without decimals
    if "invoice_date_raw" in df.columns:
        # Try multiple parsing methods
        # Method 1: Convert to float first, then to int to remove decimals, then to string
        try:
            df["invoice_date_clean"] = pd.to_numeric(df["invoice_date_raw"], errors="coerce").fillna(0).astype(int).astype(str).str.zfill(8)
            # Parse YYYYMMDD format
            df["invoice_date"] = pd.to_datetime(df["invoice_date_clean"], format="%Y%m%d", errors="coerce")
            # Drop temporary columns
            df.drop(columns=["invoice_date_clean"], inplace=True, errors="ignore")
        except Exception:
            # Fallback: try direct string conversion
            df["invoice_date_raw"] = df["invoice_date_raw"].astype(str).str.strip().str.replace('.0', '', regex=False)
            df["invoice_date"] = pd.to_datetime(df["invoice_date_raw"], format="%Y%m%d", errors="coerce")
    
    if "invoice_ship_date" in df.columns:
        _normalise_dates(df, ["invoice_ship_date"])
    
    # Note: Date filtering is handled in the dashboard to allow for YTD vs Prior Year comparison
    # The loader does NOT filter by date to load all available data

    # Normalize fields
    if "supplier_number" in df.columns:
        df["supplier_number"] = df["supplier_number"].fillna("").astype(str).str.strip()
    if "sku" in df.columns:
        df["sku"] = df["sku"].astype(str).str.strip()
    if "item_description" in df.columns:
        df["item_description"] = df["item_description"].apply(lambda v: v.strip() if isinstance(v, str) else v)
    if "manufacturer" in df.columns:
        df["manufacturer"] = df["manufacturer"].fillna("").astype(str).str.strip()
    if "price_class_desc" in df.columns:
        df["price_class_desc"] = df["price_class_desc"].apply(lambda v: v.strip() if isinstance(v, str) else "")
    if "cost_center_desc" in df.columns:
        df["cost_center_desc"] = df["cost_center_desc"].apply(lambda v: v.strip() if isinstance(v, str) else "")
    
    # Convert extended_price_usd to numeric
    if "extended_price_usd" in df.columns:
        df["extended_price_usd"] = pd.to_numeric(df["extended_price_usd"], errors="coerce").fillna(0.0)
    
    # Convert gross_profit_usd to numeric
    if "gross_profit_usd" in df.columns:
        df["gross_profit_usd"] = pd.to_numeric(df["gross_profit_usd"], errors="coerce").fillna(0.0)

    return df


def load_inventory_costs(connection_string: str) -> pd.DataFrame:
    """Load inventory cost data for ROI calculation.
    
    Returns total cost by SKU and price class for stocking items only.
    """
    sql = queries.INVENTORY_COSTS
    df = read_dataframe(connection_string, sql)
    
    if df.empty:
        return df
    
    # Normalize fields
    if "sku" in df.columns:
        df["sku"] = df["sku"].astype(str).str.strip()
    if "price_class" in df.columns:
        df["price_class"] = df["price_class"].fillna("").astype(str).str.strip()
    if "price_class_desc" in df.columns:
        df["price_class_desc"] = df["price_class_desc"].apply(lambda v: v.strip() if isinstance(v, str) else "")
    
    # Ensure total_cost is numeric
    if "total_cost" in df.columns:
        df["total_cost"] = pd.to_numeric(df["total_cost"], errors="coerce").fillna(0.0)
    
    return df


def load_sales_rep_orders(connection_string: str) -> pd.DataFrame:
    """Load order-level data for sales rep performance analysis.
    
    Returns validated orders with rep attribution, customer, revenue, and margin data.
    Excludes orders with null/blank/zero ORDER# per requirements.
    """
    sql = queries.SALES_REP_ORDERS
    df = read_dataframe(connection_string, sql)
    
    if df.empty:
        return pd.DataFrame(columns=[
            "order_number", "line_number", "order_date", "account_number", 
            "customer_name", "salesperson", "line_revenue", "line_gross_profit",
            "quantity_ordered", "item_number", "product_category", 
            "price_class", "price_class_desc"
        ])
    
    # Parse ORDER_DATE_MMDDYY (MMDDYY format, e.g., 081125 = Aug 11, 2025)
    if "order_date_mmddyy" in df.columns:
        try:
            # Convert to string and parse MMDDYY
            df["order_date_str"] = pd.to_numeric(df["order_date_mmddyy"], errors="coerce").fillna(0).astype(int).astype(str).str.zfill(6)
            
            # Extract MM, DD, YY
            df["month"] = df["order_date_str"].str[0:2]
            df["day"] = df["order_date_str"].str[2:4]
            df["year"] = df["order_date_str"].str[4:6]
            
            # Convert YY to YYYY (assume 20XX for years <= current year, 19XX for future dates)
            current_year_2digit = date.today().year % 100
            df["year_full"] = df["year"].astype(int).apply(
                lambda yy: 2000 + yy if yy <= current_year_2digit else 1900 + yy
            )
            
            # Construct date
            df["order_date"] = pd.to_datetime(
                df["year_full"].astype(str) + df["month"] + df["day"],
                format="%Y%m%d",
                errors="coerce"
            )
            
            # Drop temporary columns
            df.drop(columns=["order_date_str", "month", "day", "year", "year_full"], inplace=True, errors="ignore")
        except Exception:
            df["order_date"] = pd.NaT
    
    # Normalize fields
    if "order_number" in df.columns:
        df["order_number"] = df["order_number"].astype(str).str.strip()
    if "account_number" in df.columns:
        df["account_number"] = df["account_number"].astype(str).str.strip()
    if "customer_name" in df.columns:
        df["customer_name"] = df["customer_name"].apply(lambda v: v.strip() if isinstance(v, str) else "")
    if "salesperson" in df.columns:
        df["salesperson"] = df["salesperson"].apply(lambda v: v.strip() if isinstance(v, str) else "")
    if "product_category" in df.columns:
        df["product_category"] = df["product_category"].apply(lambda v: v.strip() if isinstance(v, str) else "")
    if "price_class_desc" in df.columns:
        df["price_class_desc"] = df["price_class_desc"].apply(lambda v: v.strip() if isinstance(v, str) else "")
    
    # Convert numeric fields
    for col in ["line_revenue", "line_gross_profit", "line_cost_per_unit", "quantity_ordered"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    
    return df


def load_account_assignments(connection_string: str) -> pd.DataFrame:
    """Load account assignment data from BILLSLMN table.
    
    Args:
        connection_string: Database connection string
    
    Returns DataFrame with columns:
    - account_number: Account number (BSACCT)
    - salesman_number: Salesman number (BSSLMN)
    - cost_center: Cost center code (BSCODE)
    
    Each row represents a rep's responsibility for an account-category pair.
    """
    df = read_dataframe(connection_string, queries.ACCOUNT_ASSIGNMENTS)
    
    # Normalize string fields
    df["account_number"] = df["account_number"].astype(str).str.strip()
    df["salesman_number"] = df["salesman_number"].astype(str).str.strip()
    df["cost_center"] = df["cost_center"].astype(str).str.strip()
    
    # Remove any duplicates
    df = df.drop_duplicates(subset=["account_number", "salesman_number", "cost_center"])
    
    return df


def load_cca_account_groups(connection_string: str) -> pd.DataFrame:
    """Load CCA account grouping rows from BILL_CD (MP + ACA/ACP/AC1)."""
    df = read_dataframe(connection_string, queries.CCA_ACCOUNT_GROUPS)
    if df.empty:
        return pd.DataFrame(columns=["account_number", "group_code", "category_code"])

    if "account_number" in df.columns:
        s = df["account_number"].astype(str).str.strip()
        n = pd.to_numeric(s, errors="coerce")
        df["account_number"] = s
        df.loc[n.notna(), "account_number"] = n.loc[n.notna()].astype("Int64").astype(str)

    if "group_code" in df.columns:
        df["group_code"] = df["group_code"].astype(str).str.strip().str.upper()
    if "category_code" in df.columns:
        df["category_code"] = df["category_code"].astype(str).str.strip().str.upper()

    df = df.drop_duplicates(subset=["account_number", "group_code", "category_code"])
    return df


def load_cca_sales_orders(
    connection_string: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> pd.DataFrame:
    """Load CCA sales orders from _ORDERS without inventory-only item filtering.

    Date filtering is applied in SQL as OR across entry/ship/invoice ship dates,
    then dates are normalized again in the returned frame for downstream consistency.
    """
    sql = queries.CCA_SALES_ORDERS
    params: Dict[str, str] = {}

    if start_date or end_date:
        entry_clause, entry_params = _format_date_bounds(
            "CONVERT(date, CONVERT(varchar(8), o.[ORDER_ENTRY_DATE_YYYYMMDD]), 112)",
            start_date,
            end_date,
        )
        ship_clause, ship_params = _format_date_bounds(
            "CONVERT(date, o.[ORDER_SHIP_DATE])",
            start_date,
            end_date,
        )
        inv_clause, inv_params = _format_date_bounds(
            "CONVERT(date, o.[INVOICE_SHIP_DATE])",
            start_date,
            end_date,
        )
        sub_clauses = []
        if entry_clause:
            sub_clauses.append(f"({entry_clause})")
        if ship_clause:
            sub_clauses.append(f"({ship_clause})")
        if inv_clause:
            sub_clauses.append(f"({inv_clause})")
        if sub_clauses:
            sql = _append_filter(sql, "(" + " OR ".join(sub_clauses) + ")")
            params.update(entry_params)
            params.update(ship_params)
            params.update(inv_params)

    df = read_dataframe(connection_string, sql, params=params or None)
    if df.empty:
        return pd.DataFrame(columns=[
            "order_number", "line_number", "account_number", "bank_name2", "salesperson_desc",
            "extended_price_no_funds", "invoice_number", "order_entry_date", "order_ship_date",
            "invoice_ship_date", "cost_center_desc", "cost_center", "sku",
        ])

    _normalise_dates(df, ["order_ship_date", "invoice_ship_date"])
    df["order_entry_date"] = pd.to_datetime(df.get("order_entry_date_raw"), format="%Y%m%d", errors="coerce")

    # Normalize identifiers and key dimensions
    for col in ["order_number", "line_number", "account_number", "invoice_number", "sku", "bank_name2", "salesperson_desc", "cost_center_desc", "cost_center"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    if "extended_price_no_funds" in df.columns:
        df["extended_price_no_funds"] = pd.to_numeric(df["extended_price_no_funds"], errors="coerce").fillna(0.0)

    return df
