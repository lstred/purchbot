from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, List, Optional, Set, Tuple
from time import perf_counter

import numpy as np
import pandas as pd

from app.config import get_config
from app.data import loaders, backorder_store
from app.data.seasonality_store import get_for_cost_center
from app.data.launch_store import update_launch_dates_from_rolls, get_launch_mapping
from app.data.stockturn_store import get_target_for_cc
from app.data.history_store import append_metrics_snapshot
from .sku_rating import assign_sku_ratings


@dataclass(slots=True)
class MetricsFilters:
    cost_centers: List[str]
    start_date: Optional[date]
    end_date: Optional[date]
    # Optional: limit scope to specific suppliers (ISUPP# from ITEM table)
    suppliers: Optional[List[str]] = None
    # Optional: limit scope to specific price class descriptions (from PRICE table)
    price_class_descs: Optional[List[str]] = None
    # Optional: limit scope to specific price class codes (IPRCCD from ITEM/PRICE tables)
    # Not in the original API; may be attached dynamically by the UI.
    # Use getattr in compute to read it if present.
    price_class_codes: Optional[List[str]] = None


def _resolve_cost_centers(requested: Optional[Iterable[str]]) -> List[str]:
    config = get_config()
    def _exclude_1(values: Iterable[str]) -> List[str]:
        return [cc for cc in values if not str(cc).strip().startswith("1")]

    if requested:
        values = sorted({cc.strip() for cc in requested if cc})
        values = _exclude_1(values)
        if values:
            return values
    return _exclude_1(config.default_cost_centers)


def _normalize_date_range(start: Optional[date], end: Optional[date]) -> tuple[Optional[date], Optional[date]]:
    if start and end and start > end:
        start, end = end, start
    return start, end


def _standardize_unit(
    quantity: pd.Series,
    unit: pd.Series,
    width_inches: pd.Series,
    fallback_width: pd.Series | float | None = None,
    cost_center: pd.Series | None = None,
) -> pd.Series:
    """Convert heterogeneous units into square yards (SY).
    
    Args:
        cost_center: Optional Series of cost centers. For SF units, division by 9
                     only applies when cost_center is in ['010', '012', '013', '011'].
    """
    # Canonicalize unit strings to be robust to punctuation and spacing (e.g., "IN.", "SQ. FT.")
    unit_upper = (
        unit.fillna("")
        .astype(str)
        .str.upper()
        .str.strip()
        # Remove punctuation and whitespace but preserve digits (so FT2 stays FT2)
        .str.replace(r"[^A-Z0-9]", "", regex=True)
    )
    qty = pd.to_numeric(quantity, errors="coerce").fillna(0.0)
    width = pd.to_numeric(width_inches, errors="coerce")

    if fallback_width is not None:
        if isinstance(fallback_width, pd.Series):
            width = width.fillna(pd.to_numeric(fallback_width, errors="coerce"))
        else:
            width = width.fillna(float(fallback_width))

    width = width.replace({0: np.nan})

    result = pd.Series(0.0, index=qty.index, dtype="float64")

    # Map canonicalized tokens to measurement families
    # Note: after cleaning, examples:
    #  - "SQ. YD." => "SQYD"; "SQ FT" => "SQFT"; "IN." => "IN"
    sy_mask = unit_upper.isin({"SY", "SQY", "SQYD", "SQYDS", "SQYARD", "SQYARDS"})
    result.loc[sy_mask] = qty.loc[sy_mask]

    # SF (square feet) conversion: only divide by 9 for specific cost centers
    sf_mask = unit_upper.isin({"SF", "SQF", "FT2", "SQFT", "SQFTS", "SFT"})
    if sf_mask.any():
        # Determine which SF entries should be divided by 9 (specific cost centers only)
        if cost_center is not None and isinstance(cost_center, pd.Series):
            cc_normalized = cost_center.astype(str).str.strip()
            sf_convert_mask = sf_mask & cc_normalized.isin(['010', '012', '013', '011'])
            sf_noconvert_mask = sf_mask & ~cc_normalized.isin(['010', '012', '013', '011'])
            result.loc[sf_convert_mask] = qty.loc[sf_convert_mask] / 9.0
            result.loc[sf_noconvert_mask] = qty.loc[sf_noconvert_mask]
        else:
            # If no cost center provided, use raw quantity (don't divide)
            result.loc[sf_mask] = qty.loc[sf_mask]

    ly_mask = unit_upper.isin({"LY", "YD", "YDS", "YARD", "YARDS"})
    if ly_mask.any():
        ly_idx = unit_upper[ly_mask].index
        w = width.loc[ly_idx]
        q = qty.loc[ly_idx]
        # If width is missing/<=0, fall back to summing raw quantities per request
        result.loc[ly_idx] = np.where(w.notna(), (q * w) / 36.0, q)

    lf_mask = unit_upper.isin({"LF", "FT", "FEET", "FOOT"})
    if lf_mask.any():
        lf_idx = unit_upper[lf_mask].index
        w = width.loc[lf_idx]
        q = qty.loc[lf_idx]
        result.loc[lf_idx] = np.where(w.notna(), (q * w) / 108.0, q)

    inch_mask = unit_upper.isin({"IN", "INCH", "INCHES"})
    if inch_mask.any():
        inch_idx = unit_upper[inch_mask].index
        w = width.loc[inch_idx]
        q = qty.loc[inch_idx]
        result.loc[inch_idx] = np.where(w.notna(), (q * w) / 1296.0, q)

    remaining = ~(sy_mask | sf_mask | ly_mask | lf_mask | inch_mask)
    result.loc[remaining] = qty.loc[remaining]

    return result.fillna(0.0)


def _safe_series(df: pd.DataFrame, column: str, dtype: str | None = None) -> pd.Series:
    """Return a Series for df[column]; if missing, return an empty Series aligned to df.index.

    This prevents scalar returns from pd.to_numeric(...), which then break on .fillna().
    """
    s = df.get(column)
    if isinstance(s, pd.Series):
        return s
    # choose a sensible default dtype
    dty = dtype if dtype is not None else "float64"
    return pd.Series(index=df.index, dtype=dty)


def _compute_actual_ship_date(df: pd.DataFrame) -> pd.Series:
    # Guard against missing columns or empty frames by providing aligned empty Series
    idx = df.index
    inv_raw = df.get("invoice_number")
    if inv_raw is None or not hasattr(inv_raw, "reindex"):
        inv_raw = pd.Series(index=idx, dtype="float64")
    invoice = pd.to_numeric(inv_raw, errors="coerce").fillna(0)

    inv_ship_raw = df.get("invoice_ship_date")
    if inv_ship_raw is None or not hasattr(inv_ship_raw, "reindex"):
        inv_ship_raw = pd.Series(index=idx, dtype="datetime64[ns]")
    invoice_ship = pd.to_datetime(inv_ship_raw, errors="coerce")

    ord_ship_raw = df.get("order_ship_date")
    if ord_ship_raw is None or not hasattr(ord_ship_raw, "reindex"):
        ord_ship_raw = pd.Series(index=idx, dtype="datetime64[ns]")
    order_ship = pd.to_datetime(ord_ship_raw, errors="coerce")

    actual = order_ship.copy()
    mask = invoice > 0
    try:
        actual.loc[mask] = invoice_ship.loc[mask]
    except Exception:
        # Best-effort alignment if indices differ
        aligned = invoice_ship.reindex(actual.index)
        actual.loc[mask] = aligned.loc[mask]
    return actual


def _identify_backorders(detail_col: pd.Series) -> pd.Series:
    """Identify true backorders by strict status codes.

    Only consider rows with DETAIL_LINE_STATUS exactly 'R' or 'B' (case-insensitive),
    excluding blanks or any other values. This avoids misclassifying blanks or
    non-numeric statuses as backorders.
    """
    detail = detail_col.fillna("").astype(str).str.strip().str.upper()
    return detail.isin(["R", "B"])  # strict match per requirement


def _calculate_average_daily_sales(df: pd.DataFrame, start: Optional[date], end: Optional[date]) -> pd.Series:
    if df.empty:
        return pd.Series(dtype="float64")

    window_start = start or (df["order_entry_date"].min() or date.today())
    window_end = end or (df["order_entry_date"].max() or date.today())
    if isinstance(window_start, pd.Timestamp):
        window_start = window_start.date()
    if isinstance(window_end, pd.Timestamp):
        window_end = window_end.date()

    sku_sales = df.groupby("sku", dropna=False)["quantity_sy"].sum()

    # Launch-aware ADS window per SKU (if provided by caller).
    # This allows newer price classes to use elapsed days since launch rather than the full report window.
    if "ads_start_date" in df.columns:
        sku_start = pd.to_datetime(df.get("ads_start_date"), errors="coerce").groupby(df.get("sku"), dropna=False).min()
        if start is not None:
            global_start_ts = pd.Timestamp(start)
            # Effective start is the later of global report start and launch-aware start.
            sku_start = sku_start.fillna(global_start_ts)
            sku_start = pd.Series(
                np.maximum(sku_start.values.astype("datetime64[ns]"), np.array(global_start_ts.to_datetime64())),
                index=sku_start.index,
            )
        else:
            sku_start = sku_start.fillna(pd.Timestamp(window_start))

        end_ts = pd.Timestamp(window_end)
        days_by_sku = ((end_ts - sku_start).dt.days).clip(lower=1)
        return sku_sales.div(days_by_sku, fill_value=np.nan).fillna(0.0)

    days = max((window_end - window_start).days, 1)
    return sku_sales / days


def _merge_lead_time(items: pd.DataFrame, product_lines: pd.DataFrame) -> pd.Series:
    if items.empty:
        return pd.Series(dtype="float64")

    merged = items.merge(
        product_lines[["product_line", "manufacturer", "product_line_lead_time_days"]],
        on=["product_line", "manufacturer"],
        how="left",
        suffixes=("", "_pl"),
    )

    merged.set_index("sku", inplace=True)

    item_lead = pd.to_numeric(merged["item_lead_time_days"], errors="coerce").mask(lambda s: s <= 0)
    prod_lead = pd.to_numeric(merged["product_line_lead_time_days"], errors="coerce").mask(lambda s: s <= 0)
    return item_lead.fillna(prod_lead).rename("nominal_lead_time_days")


def _actual_lead_time_from_receipts(purchase_orders: pd.DataFrame, receipts: pd.DataFrame) -> pd.Series:
    if purchase_orders.empty or receipts.empty:
        return pd.Series(dtype="float64", name="actual_lead_time_days")

    receipts_subset = receipts[["purchase_order_number", "sku", "receipt_date"]].dropna()
    po_subset = purchase_orders[["order_number", "sku", "order_entry_date"]].dropna()

    # Normalize ID fields to consistent string format (e.g., 1.0 -> "1", preserve non-numeric)
    def _norm_id(s: pd.Series) -> pd.Series:
        s = s.astype(str).str.strip()
        num = pd.to_numeric(s, errors="coerce")
        out = s.copy()
        mask = num.notna()
        out.loc[mask] = num.loc[mask].astype("Int64").astype(str)
        return out

    receipts_subset["purchase_order_number"] = _norm_id(receipts_subset["purchase_order_number"]) if "purchase_order_number" in receipts_subset.columns else ""
    po_subset["order_number"] = _norm_id(po_subset["order_number"]) if "order_number" in po_subset.columns else ""

    merged = receipts_subset.merge(
        po_subset,
        left_on=["purchase_order_number", "sku"],
        right_on=["order_number", "sku"],
        how="inner",
    )
    if merged.empty:
        return pd.Series(dtype="float64", name="actual_lead_time_days")

    merged["actual_lead_time_days"] = (
        merged["receipt_date"] - merged["order_entry_date"]
    ).dt.days
    merged["actual_lead_time_days"] = pd.to_numeric(merged["actual_lead_time_days"], errors="coerce").mask(lambda s: s <= 0)

    return (
        merged.groupby("sku")["actual_lead_time_days"].median().rename("actual_lead_time_days")
    )


def _compute_period_days(sales_orders: pd.DataFrame, config_default_days: int) -> int:
    if sales_orders.empty:
        return config_default_days

    min_date = sales_orders["order_entry_date"].min()
    max_date = sales_orders["order_entry_date"].max()
    if pd.isna(min_date) or pd.isna(max_date):
        return config_default_days

    days = max((max_date - min_date).days, 1)
    return max(days, 30)


def _make_sku_frame(indices: Set[str]) -> pd.DataFrame:
    if not indices:
        df = pd.DataFrame(columns=["sku"]).set_index("sku")
    else:
        df = pd.DataFrame(index=sorted(indices))
    df.index.name = "sku"
    return df


def _compute_summary_metrics(sku_metrics: pd.DataFrame) -> Dict[str, float]:
    if sku_metrics.empty:
        return {
            "stock_turn": 0.0,
            "fill_rate": 0.0,
            "days_of_inventory": float("inf"),
            "aging_bad_sku_count": 0,
            "runout_sku_count": 0,
            "total_skus": 0,
        }

    total_orders = sku_metrics["orders_count"].sum()
    total_backorders = sku_metrics["backorder_count"].sum()
    fill_rate = 1 - (total_backorders / total_orders) if total_orders else 0.0

    # Stock turn per request: (annualized quantity) / (inventory)
    # Use total annualized sales across SKUs to avoid median = 0 when many SKUs have zero turn
    total_avg_daily = pd.to_numeric(sku_metrics.get("avg_daily_sales_sy"), errors="coerce").fillna(0).sum()
    total_inventory = pd.to_numeric(sku_metrics.get("inventory_sy"), errors="coerce").fillna(0).sum()
    stock_turn = (total_avg_daily * 365.0) / total_inventory if total_inventory > 0 else 0.0

    days_of_inventory = sku_metrics["days_of_inventory"].replace([np.inf, -np.inf], np.nan).median()

    aging_bad = (sku_metrics["days_since_last_sale"] >= 18 * 30).sum()
    runout = sku_metrics["runout_risk"].sum()

    return {
        "stock_turn": float(stock_turn) if pd.notna(stock_turn) else 0.0,
        "fill_rate": float(max(min(fill_rate, 1.0), 0.0)),
        "days_of_inventory": float(days_of_inventory) if pd.notna(days_of_inventory) else float("inf"),
        "aging_bad_sku_count": int(aging_bad),
        "runout_sku_count": int(runout),
        "total_skus": int(len(sku_metrics)),
    }


def _compute_monthly_seasonality_user(cost_centers: Iterable[str]) -> Dict[str, pd.Series]:
    """Load user-provided monthly seasonality per cost center from seasonality_store.

    If a cost center is missing, fall back to equal distribution. Always returns entries for
    provided cost centers; also includes a "__default__" key as a universal fallback.
    """
    out: Dict[str, pd.Series] = {}
    for cc in cost_centers or ["__default__"]:
        out[str(cc)] = get_for_cost_center(str(cc))
    if "__default__" not in out:
        out["__default__"] = get_for_cost_center(None)
    return out


def _seasonal_window_multiplier(month_pct: pd.Series, start: date, horizon_days: int) -> float:
    """Sum of daily multipliers across the horizon given monthly pct distribution.

    Daily multiplier for month m is: (pct_m * 365 / days_in_month).
    Returns the sum of multipliers for each day in the horizon (unit: days).
    """
    if horizon_days <= 0:
        return 0.0
    # Fallback equal distribution if needed
    if not isinstance(month_pct, pd.Series) or month_pct.empty:
        month_pct = pd.Series({m: 1.0 / 12.0 for m in range(1, 13)})

    import calendar as _cal
    remaining = int(max(round(horizon_days), 0))
    current = start
    total_multiplier = 0.0
    while remaining > 0:
        dim = _cal.monthrange(current.year, current.month)[1]
        days_left_in_month = dim - current.day + 1
        take = min(remaining, days_left_in_month)
        m = current.month
        pct_m = float(month_pct.get(m, 1.0 / 12.0))
        daily_mult = pct_m * 365.0 / float(dim)
        total_multiplier += daily_mult * float(take)
        # advance to next month
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
        remaining -= take
    return float(total_multiplier)


def compute_dashboard_data(filters: MetricsFilters) -> Dict[str, object]:
    config = get_config()
    # Timing instrumentation
    timings: list[tuple[str, float]] = []
    t_prev = perf_counter()
    def tmark(step: str):
        nonlocal t_prev
        now = perf_counter()
        timings.append((step, now - t_prev))
        t_prev = now
    cost_centers = _resolve_cost_centers(filters.cost_centers)
    start, end = _normalize_date_range(filters.start_date, filters.end_date)

    items = loaders.load_items(config.connection_string, cost_centers)
    tmark("load_items")
    # Also load a global items view (no CC filter) to enrich attributes like price_class for SKUs
    # that may not be present in the CC-scoped items list (prevents losing launch/JSTOCK logic)
    try:
        items_all = loaders.load_items(config.connection_string, None)
    except Exception:
        items_all = pd.DataFrame()
    price_classes = loaders.load_price_classes(config.connection_string)
    tmark("load_price_classes")
    product_lines = loaders.load_product_lines(config.connection_string)
    tmark("load_product_lines")

    if not price_classes.empty:
        items = items.merge(price_classes, on="price_class", how="left")
    tmark("merge_price_classes")

    # Apply supplier filter if provided
    selected_suppliers = set((filters.suppliers or []))
    if selected_suppliers and "supplier_number" in items.columns:
        items = items[items["supplier_number"].isin(selected_suppliers)].copy()

    # Apply price class filters if provided (codes preferred; fallback to descriptions)
    selected_pc_codes = set(getattr(filters, "price_class_codes", []) or [])
    if selected_pc_codes and "price_class" in items.columns:
        # Normalize to strings for safe matching
        items = items[items["price_class"].astype(str).isin({str(c) for c in selected_pc_codes})].copy()
    else:
        selected_pclasses = set(getattr(filters, "price_class_descs", []) or [])
        if selected_pclasses and "price_class_desc" in items.columns:
            items = items[items["price_class_desc"].isin(selected_pclasses)].copy()

    # Remove any duplicate item rows by SKU to avoid duplicate joins downstream
    if not items.empty and "sku" in items.columns:
        items = items.drop_duplicates(subset=["sku"]).copy()
    # Compute base sku = IIXREF if present, else SKU. This lets us include bases even if their row is missing.
    if not items.empty:
        iix = items.get("iixref")
        if iix is not None:
            base_sku = iix.fillna("").astype(str).str.strip()
            base_sku = base_sku.mask(base_sku.eq(""), items["sku"].astype(str))
        else:
            base_sku = items["sku"].astype(str)
        items = items.copy()
        items["base_sku"] = base_sku
    else:
        items["base_sku"] = pd.Series(dtype="object")
    # Build a representative per-base SKU view for attributes/widths (CC-scoped)
    if not items.empty:
        items_base = (
            items.sort_values(["sku"]).drop_duplicates(subset=["base_sku"], keep="first").copy()
        )
    else:
        items_base = items.copy()
    # Build a global per-base SKU view (unscoped) for attributes like price_class used in launch mapping
    if isinstance(items_all, pd.DataFrame) and not items_all.empty:
        iix_all = items_all.get("iixref")
        if iix_all is not None:
            base_all = iix_all.fillna("").astype(str).str.strip()
            base_all = base_all.mask(base_all.eq(""), items_all["sku"].astype(str))
        else:
            base_all = items_all["sku"].astype(str)
        items_all = items_all.copy()
        items_all["base_sku"] = base_all
        items_all_base = items_all.sort_values(["sku"]).drop_duplicates(subset=["base_sku"], keep="first").copy()
    else:
        items_all_base = pd.DataFrame(columns=["base_sku","price_class"])  # minimal
    # Allowed SKUs are all base_sku values present
    allowed_skus = set(items.get("base_sku", []))
    # Width maps by base_sku: CC-scoped and global (fallback)
    width_map = items_base.set_index("base_sku")["item_width_inches"] if (not items_base.empty and "item_width_inches" in items_base.columns) else pd.Series(dtype=float)
    width_map_global = items_all_base.set_index("base_sku")["item_width_inches"] if (isinstance(items_all_base, pd.DataFrame) and not items_all_base.empty and "item_width_inches" in items_all_base.columns) else pd.Series(dtype=float)

    sales_orders = loaders.load_orders(config.connection_string, cost_centers, start, end)
    tmark("load_orders")
    # For on-order quantities, include future ETAs and recently past ETAs (to catch delays).
    # Start from the earlier of the selected start date and (today - 120 days). No end bound.
    from datetime import timedelta
    po_start = start or date.today()
    try:
        # Include ETAs within the last 12 months to capture delayed/overdue POs
        po_start = min(po_start, date.today() - timedelta(days=365))
    except Exception:
        po_start = date.today() - timedelta(days=365)
    purchase_orders = loaders.load_purchase_orders(config.connection_string, cost_centers, po_start, None)
    tmark("load_purchase_orders")

    def _normalize_id(series: pd.Series) -> pd.Series:
        """Normalize numeric-like IDs so '1', '1.0', '001' all become '1'.
        Falls back to stripped string when not numeric.
        """
        s = series.astype(str).str.strip()
        num = pd.to_numeric(s, errors="coerce")
        normalized = s.copy()
        is_num = num.notna()
        # Format integers without decimals; otherwise keep original string
        normalized.loc[is_num] = num.loc[is_num].astype("Int64").astype(str)
        return normalized

    if not sales_orders.empty:
        sales_orders["order_number"] = _normalize_id(sales_orders["order_number"]) if "order_number" in sales_orders.columns else ""
        if "line_number" in sales_orders.columns:
            sales_orders["line_number"] = _normalize_id(sales_orders["line_number"])  # handles blanks
        else:
            sales_orders["line_number"] = ""
        sales_orders["order_line_id"] = sales_orders["order_number"] + "-" + sales_orders["line_number"]
    else:
        sales_orders["order_line_id"] = pd.Series(dtype="object")
    tmark("sales_ids")
    # Load rolls without CC filter to avoid missing inventory for SKUs whose item CC differs
    rolls = loaders.load_rolls(config.connection_string, None)
    tmark("load_rolls")
    receipts = loaders.load_open_receipts(config.connection_string)
    # Partially received POs (OPENPO_D)
    try:
        openpo_partials = loaders.load_openpo_partials(config.connection_string)
    except Exception:
        openpo_partials = pd.DataFrame(columns=["sku", "partial_received_po"])
    # Pending POs (OPENPO_D) to compute PO column as sum(QTYO)-sum(QTYP)
    try:
        openpo_pending = loaders.load_openpo_pending(config.connection_string)
    except Exception:
        openpo_pending = pd.DataFrame(columns=["sku", "po_pending_qty"])
    tmark("load_receipts")
    # Load ITEMSTK target stock (JSTOCK)
    try:
        itemstks = loaders.load_itemstks(config.connection_string)
    except Exception:
        itemstks = pd.DataFrame(columns=["sku", "jstock"])  # best effort
    tmark("load_itemstks")

    # Seed launch dates for price classes using ROLLS receive dates (RLRCTD) merged by price class.
    # This runs best-effort and will not overwrite existing launch dates.
    try:
        _ = update_launch_dates_from_rolls(items, rolls)
    except Exception:
        pass

    # Map all SKUs (alias or base) to their base_sku derived above
    try:
        if not items.empty and "base_sku" in items.columns:
            full_map = dict(zip(items["sku"].astype(str), items["base_sku"].astype(str)))
            if full_map:
                if not sales_orders.empty and "sku" in sales_orders.columns:
                    sales_orders["sku"] = sales_orders["sku"].astype(str).map(lambda x: full_map.get(x, x))
                if not purchase_orders.empty and "sku" in purchase_orders.columns:
                    purchase_orders["sku"] = purchase_orders["sku"].astype(str).map(lambda x: full_map.get(x, x))
                if not rolls.empty and "sku" in rolls.columns:
                    rolls["sku"] = rolls["sku"].astype(str).map(lambda x: full_map.get(x, x))
                if isinstance(openpo_partials, pd.DataFrame) and not openpo_partials.empty and "sku" in openpo_partials.columns:
                    openpo_partials["sku"] = openpo_partials["sku"].astype(str).map(lambda x: full_map.get(x, x))
                try:
                    if isinstance(openpo_pending, pd.DataFrame) and not openpo_pending.empty and "sku" in openpo_pending.columns:
                        openpo_pending["sku"] = openpo_pending["sku"].astype(str).map(lambda x: full_map.get(x, x))
                except Exception:
                    pass
                # After remapping SKUs to base, backfill missing widths from items_base and recompute quantity_sy for sales orders
                try:
                    if not sales_orders.empty:
                        # STRICT RULE: Only use width-based conversion when the order line has a
                        # positive ITEM_WIDTH_INCHES_IF_R. Otherwise, treat the quantity as SY (sum numbers).
                        sales_orders.loc[:, "line_width_inches"] = pd.to_numeric(
                            sales_orders.get("item_width_inches"), errors="coerce"
                        )
                        sales_orders.loc[:, "line_width_inches"] = sales_orders["line_width_inches"].replace({0: np.nan})
                        sales_orders.loc[:, "quantity_sy"] = _standardize_unit(
                            sales_orders.get("quantity_ordered"),
                            sales_orders.get("unit_of_measure"),
                            sales_orders["line_width_inches"],
                            cost_center=sales_orders.get("cost_center"),
                        )
                except Exception:
                    pass
    except Exception:
        pass

    # Do not hard-filter by allowed_skus to avoid dropping valid SKUs that exist in sales/rolls/POs but lack a base row in items

    # Do not exclude account_number == 1 for sales orders; keep all to correctly count backorders

    
    # Guard against future-dated order entries sneaking in due to upstream data issues
    today_ts = pd.Timestamp(date.today())
    sales_orders = sales_orders.loc[(sales_orders["order_entry_date"].isna()) | (sales_orders["order_entry_date"] <= today_ts)].copy()
    sales_orders["actual_ship_date"] = _compute_actual_ship_date(sales_orders)
    # Keep a copy before excluding account_number == 1 so backorder history can capture all R/B lines
    so_all_accounts = sales_orders.copy()
    # Exclude purchase-order lines from sales velocity only (retain all for history)
    # Be robust to missing/empty account_number to avoid scalar to_numeric issues
    _acct_raw = sales_orders.get("account_number")
    if _acct_raw is None or not hasattr(_acct_raw, "reindex"):
        _acct_raw = pd.Series(index=sales_orders.index, dtype="float64")
    acct_numeric = pd.to_numeric(_acct_raw, errors="coerce").fillna(0)
    sales_orders = sales_orders.loc[acct_numeric > 1].copy()
    _detail_series = sales_orders.get("detail_line_status")
    if not isinstance(_detail_series, pd.Series):
        _detail_series = pd.Series(index=sales_orders.index, dtype=object)
    sales_orders["backorder_flag"] = _identify_backorders(_detail_series)
    # Exclude non-positive quantities from metrics
    qty_sy_series_all = pd.to_numeric(_safe_series(sales_orders, "quantity_sy"), errors="coerce").fillna(0)
    sales_orders = sales_orders.loc[qty_sy_series_all > 0].copy()
    # Compute backorder flag and positive qty filter for all-accounts copy (for history persistence)
    _detail_series_all = so_all_accounts.get("detail_line_status")
    if not isinstance(_detail_series_all, pd.Series):
        _detail_series_all = pd.Series(index=so_all_accounts.index, dtype=object)
    so_all_accounts["backorder_flag"] = _identify_backorders(_detail_series_all)
    qty_sy_series_all_acct = pd.to_numeric(_safe_series(so_all_accounts, "quantity_sy"), errors="coerce").fillna(0)
    so_all_accounts = so_all_accounts.loc[qty_sy_series_all_acct > 0].copy()
    # Pre-compute per-SKU total backordered quantity (all-time) using orders without date bounds.
    # Use strict 'B' status only (exclude 'R') so BO and Reorder include only true backorders.
    try:
        orders_all = loaders.load_orders(config.connection_string, cost_centers)
        if not orders_all.empty:
            # Map alias SKUs to base SKUs like sales_orders did
            if not items.empty and "base_sku" in items.columns:
                full_map = dict(zip(items["sku"].astype(str), items["base_sku"].astype(str)))
                orders_all["sku"] = orders_all.get("sku").astype(str).map(lambda x: full_map.get(x, x))
            # Width standardization for quantity_sy
            orders_all["line_width_inches"] = pd.to_numeric(orders_all.get("item_width_inches"), errors="coerce").replace({0: np.nan})
            orders_all["quantity_sy"] = _standardize_unit(
                orders_all.get("quantity_ordered"),
                orders_all.get("unit_of_measure"),
                orders_all["line_width_inches"],
                cost_center=orders_all.get("cost_center"),
            )
            detail = orders_all.get("detail_line_status", pd.Series(index=orders_all.index)).fillna("").astype(str).str.strip().str.upper()
            qty_all = pd.to_numeric(orders_all.get("quantity_sy"), errors="coerce").fillna(0.0)
            # Strict backorders for BO and Reorder: only 'B'
            mask_bo_only = detail.eq("B") & (qty_all > 0)
            # Deduplicate order lines when order/line identifiers are present
            try:
                def _normalize_id(series: pd.Series) -> pd.Series:
                    s = series.astype(str).str.strip()
                    num = pd.to_numeric(s, errors="coerce")
                    out = s.copy()
                    mask = num.notna()
                    out.loc[mask] = num.loc[mask].astype("Int64").astype(str)
                    return out
                if "order_number" in orders_all.columns:
                    orders_all["order_number"] = _normalize_id(orders_all["order_number"]) 
                if "line_number" in orders_all.columns:
                    orders_all["line_number"] = _normalize_id(orders_all["line_number"]) 
                else:
                    orders_all["line_number"] = ""
                orders_all["order_line_id"] = orders_all["order_number"] + "-" + orders_all["line_number"]
                dedup_cols = [c for c in ["order_line_id","sku"] if c in orders_all.columns]
                orders_all = orders_all.drop_duplicates(subset=dedup_cols) if dedup_cols else orders_all
            except Exception:
                pass
            # Exclude rows with missing/zero order numbers from BO
            try:
                ordnum = orders_all.get("order_number")
                if ordnum is not None:
                    ordnum_str = ordnum.astype(str).str.strip()
                    mask_ord_valid = (ordnum_str != "") & (ordnum_str != "0")
                else:
                    mask_ord_valid = pd.Series([True] * len(orders_all), index=orders_all.index)
            except Exception:
                mask_ord_valid = pd.Series([True] * len(orders_all), index=orders_all.index)

            # Exclude account_number == 1 from BO quantities per requirement
            try:
                acct_series = pd.to_numeric(_safe_series(orders_all, "account_number"), errors="coerce")
                mask_acct_ok = acct_series.ne(1)
            except Exception:
                mask_acct_ok = pd.Series([True] * len(orders_all), index=orders_all.index)

            bo_qty_by_sku = orders_all.loc[mask_bo_only & mask_ord_valid & mask_acct_ok].groupby("sku")["quantity_sy"].sum()
        else:
            bo_qty_by_sku = pd.Series(dtype=float)
    except Exception:
        bo_qty_by_sku = pd.Series(dtype=float)
    tmark("sales_preprocess")

    # Distinct order lines for counts and quantity to avoid duplication across status/ship events
    distinct_lines = sales_orders.sort_values("order_entry_date").drop_duplicates(subset=["order_line_id"], keep="first")
    # Safety: ensure required columns exist even if upstream frames are empty or missing fields
    for _df in (sales_orders, distinct_lines):
        if "sku" not in _df.columns:
            _df["sku"] = pd.Series(dtype=object)
        if "quantity_sy" not in _df.columns:
            _df["quantity_sy"] = pd.Series(dtype="float64")
        if "backorder_flag" not in _df.columns:
            _df["backorder_flag"] = pd.Series(dtype=bool)
        if "order_line_id" not in _df.columns:
            _df["order_line_id"] = pd.Series(dtype=object)

    # Aggregate per SKU
    # Sum quantity on distinct lines only to avoid double-counting
    qty_by_sku = distinct_lines.groupby("sku")["quantity_sy"].sum() if "sku" in distinct_lines.columns else pd.Series(dtype=float)
    order_count_by_sku = distinct_lines.groupby("sku")["order_line_id"].nunique() if "sku" in distinct_lines.columns else pd.Series(dtype=float)
    backorder_count_by_sku = (
        distinct_lines.loc[distinct_lines["backorder_flag"]].groupby("sku")["order_line_id"].nunique()
        if ("sku" in distinct_lines.columns) else pd.Series(dtype=float)
    )
    last_sale_by_sku = sales_orders.groupby("sku")["actual_ship_date"].max() if "sku" in sales_orders.columns else pd.Series(dtype="datetime64[ns]")
    last_order_by_sku = sales_orders.groupby("sku")["order_entry_date"].max() if "sku" in sales_orders.columns else pd.Series(dtype="datetime64[ns]")

    sku_sales = (
        pd.DataFrame({
            "quantity_sy": qty_by_sku,
            "orders_count": order_count_by_sku,
            "backorder_count": backorder_count_by_sku,
            "last_sale_date": last_sale_by_sku,
            "last_order_date": last_order_by_sku,
        })
        .fillna({"orders_count": 0, "backorder_count": 0})
    )

    # Adjust ADS window: lower bound is the price class launch date (floored to 2025-08-04) if later than selected start
    launch_map = get_launch_mapping(items_base.get("price_class") if not items_base.empty else None)
    # For per-SKU computation, we need per-SKU launch lower bounds; map via price_class
    sku_to_pc = items_base.set_index("sku")["price_class"] if (not items_base.empty and "price_class" in items_base.columns) else pd.Series(dtype=object)
    # Use distinct lines for ADS computation as well
    so_for_ads = distinct_lines.copy()
    if not so_for_ads.empty:
        so_for_ads = so_for_ads.merge(sku_to_pc.rename("price_class"), left_on="sku", right_index=True, how="left")
        so_for_ads["order_entry_date"] = pd.to_datetime(so_for_ads.get("order_entry_date"), errors="coerce")
        # Build per-row start bound: max(global start, launch date for price class)
        global_start = pd.to_datetime(start) if start else None
        def _row_start(pc):
            dt = launch_map.get(str(pc))
            return pd.Timestamp(dt) if dt else None
        launch_start = so_for_ads.get("price_class").map(_row_start)
        if global_start is not None:
            global_series = pd.Series([global_start] * len(so_for_ads), index=so_for_ads.index)
            row_start = pd.concat([launch_start, global_series], axis=1).max(axis=1)
        else:
            row_start = launch_start
        so_for_ads["ads_start_date"] = row_start
        if row_start is not None:
            mask = (so_for_ads["order_entry_date"].isna()) | (row_start.isna()) | (so_for_ads["order_entry_date"] >= row_start)
            so_for_ads = so_for_ads.loc[mask].copy()
    avg_daily_sales = _calculate_average_daily_sales(so_for_ads, start, end)
    tmark("sales_aggregate")

    if not purchase_orders.empty:
        # Map alias SKUs to base SKUs using IIXREF so on-order rolls up to base items
        try:
            alias_map = {}
            if not items.empty and "iixref" in items.columns:
                alias_df = items[["sku", "iixref"]].copy()
                alias_df["iixref"] = alias_df["iixref"].fillna("").astype(str).str.strip()
                alias_df = alias_df[alias_df["iixref"] != ""]
                alias_map = dict(zip(alias_df["sku"].astype(str), alias_df["iixref"].astype(str)))
            if alias_map:
                purchase_orders["sku"] = purchase_orders.get("sku").astype(str).map(lambda x: alias_map.get(x, x))
        except Exception:
            pass
        purchase_orders["line_width_inches"] = pd.to_numeric(purchase_orders.get("item_width_inches"), errors="coerce")
        if not width_map.empty:
            purchase_orders.loc[:, "line_width_inches"] = purchase_orders["line_width_inches"].fillna(
                purchase_orders["sku"].map(width_map)
            )
        # Standardize all units to SY using width when applicable (LY/LF need width; SY/SF don't)
        units_u = purchase_orders.get("unit_of_measure").fillna("").astype(str).str.upper()
        widths = pd.to_numeric(purchase_orders.get("line_width_inches"), errors="coerce")
        qty = pd.to_numeric(purchase_orders.get("quantity_ordered"), errors="coerce").fillna(0.0)
        purchase_orders["quantity_sy"] = _standardize_unit(qty, units_u, widths, cost_center=purchase_orders.get("cost_center"))
        # Build order_line_id for robust dedup (order + line)
        def _normalize_id(series: pd.Series) -> pd.Series:
            s = series.astype(str).str.strip()
            num = pd.to_numeric(s, errors="coerce")
            out = s.copy()
            mask = num.notna()
            out.loc[mask] = num.loc[mask].astype("Int64").astype(str)
            return out
        if "order_number" in purchase_orders.columns:
            purchase_orders["order_number"] = _normalize_id(purchase_orders["order_number"]) 
        if "line_number" in purchase_orders.columns:
            purchase_orders["line_number"] = _normalize_id(purchase_orders["line_number"])
        else:
            purchase_orders["line_number"] = ""
        purchase_orders["order_line_id"] = purchase_orders["order_number"] + "-" + purchase_orders["line_number"]
        # Prefer dedup by order_line_id and sku as the strongest key
        dedup_cols = [c for c in ["order_line_id","sku"] if c in purchase_orders.columns]
        po_distinct = purchase_orders.drop_duplicates(subset=dedup_cols) if dedup_cols else purchase_orders
        on_order = po_distinct.groupby("sku")["quantity_sy"].sum()
        tmark("on_order_aggregate")
    else:
        on_order = pd.Series(dtype="float64")

    if not rolls.empty:
        # Drop exact duplicate rows only; do not collapse different rows that share a roll_number
        rolls = rolls.drop_duplicates().copy()
        # Exclude inventory rows where RCODE/status contains 'I' anywhere.
        rcode_col = None
        for _cand in ["status_code", "Status_Code", "status", "RCODE@", "rcode@", "RCODE", "rcode"]:
            if _cand in rolls.columns:
                rcode_col = _cand
                break
        if rcode_col is not None:
            status_vals = rolls.get(rcode_col).astype(str).str.upper().str.strip()
            rolls = rolls.loc[~status_vals.str.contains("I", na=False)].copy()
        # rolls['sku'] is base sku now; join width and cost_center from items_base keyed by base_sku
        rolls = rolls.merge(
            items_base[["base_sku", "item_width_inches", "cost_center"]].rename(columns={"base_sku": "sku"}),
            on="sku",
            how="left",
        )
        # If width is 0 or missing, use available_quantity as-is per request; otherwise convert to SY
        widths = pd.to_numeric(rolls.get("item_width_inches"), errors="coerce")
        qty_avail = pd.to_numeric(rolls.get("available_quantity"), errors="coerce").fillna(0.0)
        inv_conv = _standardize_unit(
            rolls.get("available_quantity"), rolls.get("unit_of_measure"), widths, cost_center=rolls.get("cost_center")
        )
        width_missing = widths.isna() | (widths <= 0)
        rolls["inventory_sy"] = inv_conv
        rolls.loc[width_missing, "inventory_sy"] = qty_avail.loc[width_missing]
        # If unit is not 'IN', do not use width at all; use raw available quantity
        unit_u = rolls.get("unit_of_measure").fillna("").astype(str).str.upper()
        non_in = unit_u != "IN"
        rolls.loc[non_in, "inventory_sy"] = qty_avail.loc[non_in]
        # Compute weighted average inventory age per SKU based on receive_date
        today_ts = pd.Timestamp(date.today())
        receive_dt = pd.to_datetime(rolls.get("receive_date"), errors="coerce")
        age_days = (today_ts - receive_dt).dt.days
        rolls["age_days"] = age_days

        inventory = rolls.groupby("sku")["inventory_sy"].sum()

        def _weighted_age(group: pd.DataFrame) -> float:
            qty = pd.to_numeric(group.get("inventory_sy"), errors="coerce").fillna(0)
            age = pd.to_numeric(group.get("age_days"), errors="coerce")
            mask = (qty > 0) & age.notna()
            if not mask.any():
                return float("nan")
            return float((qty[mask] * age[mask]).sum() / qty[mask].sum())

        inv_age = rolls.groupby("sku").apply(_weighted_age).rename("inventory_age_days")
        tmark("inventory_aggregate")
    else:
        inventory = pd.Series(dtype="float64")
        inv_age = pd.Series(dtype="float64", name="inventory_age_days")

    # Seed index with base SKUs we know about from items, then include any from sales/on_order/inventory
    sku_index: Set[str] = set(items_base.get("base_sku", []))
    sku_index |= set(sku_sales.index)
    sku_index |= set(on_order.index)
    sku_index |= set(inventory.index)

    sku_metrics = _make_sku_frame(sku_index)
    sku_metrics = sku_metrics.join(sku_sales, how="left")
    sku_metrics = sku_metrics.join(inventory.rename("inventory_sy"), how="left")
    sku_metrics = sku_metrics.join(inv_age, how="left")
    sku_metrics = sku_metrics.join(on_order.rename("on_order_sy"), how="left")
    # Attach OPENPO_D pending quantity as the authoritative PO display value
    try:
        if isinstance(openpo_pending, pd.DataFrame) and not openpo_pending.empty:
            pend = openpo_pending.set_index("sku")["po_pending_qty"].astype(float)
            sku_metrics = sku_metrics.join(pend.rename("po_pending_qty"), how="left")
        else:
            sku_metrics["po_pending_qty"] = 0.0
    except Exception:
        sku_metrics["po_pending_qty"] = 0.0
    sku_metrics = sku_metrics.join(avg_daily_sales.rename("avg_daily_sales_sy"), how="left")
    # Join partial received PO amount if available
    try:
        if isinstance(openpo_partials, pd.DataFrame) and not openpo_partials.empty:
            pr = openpo_partials.set_index("sku")["partial_received_po"].astype(float)
            sku_metrics = sku_metrics.join(pr, how="left")
        else:
            sku_metrics["partial_received_po"] = 0.0
    except Exception:
        sku_metrics["partial_received_po"] = 0.0
    # Join backorder quantity (SY) per SKU if we computed it
    try:
        if isinstance(bo_qty_by_sku, pd.Series) and not bo_qty_by_sku.empty:
            sku_metrics = sku_metrics.join(bo_qty_by_sku.rename("backorder_qty_sy"), how="left")
        else:
            sku_metrics["backorder_qty_sy"] = 0.0
    except Exception:
        sku_metrics["backorder_qty_sy"] = 0.0
    tmark("build_sku_metrics_joins")

    sku_metrics.fillna(
        {
            "quantity_sy": 0.0,
            "orders_count": 0,
            "backorder_count": 0,
            "inventory_sy": 0.0,
            "on_order_sy": 0.0,
            "avg_daily_sales_sy": 0.0,
            "partial_received_po": 0.0,
        },
        inplace=True,
    )
    # Derive net_inventory now so it exists for dedup aggregation
    # For net inventory, use warehouse on-order estimate plus partials as before,
    # but keep po_pending_qty separately for UI display/over-ordered logic
    assumed_on_order = (
        pd.to_numeric(sku_metrics.get("on_order_sy"), errors="coerce").fillna(0.0)
        + pd.to_numeric(sku_metrics.get("partial_received_po"), errors="coerce").fillna(0.0)
    )
    sku_metrics["assumed_on_order_sy"] = assumed_on_order
    sku_metrics["net_inventory_sy"] = pd.to_numeric(sku_metrics.get("inventory_sy"), errors="coerce").fillna(0.0) + assumed_on_order

    # Enrich with item attributes using per-base representative rows
    if not items_base.empty:
        # Select columns from items_base and produce a unique 'sku' label from base_sku
        select_cols = [c for c in ["base_sku", "manufacturer", "product_line", "sku_description", "cost_center", "price_class"] if c in items_base.columns]
        ib = items_base[select_cols].rename(columns={"base_sku": "sku"})
        ib_clean = ib.drop_duplicates(subset=["sku"])
        sku_metrics = sku_metrics.reset_index().merge(ib_clean, on="sku", how="left").set_index("sku")
    tmark("enrich_attributes")

    today = pd.Timestamp(date.today())
    # Ensure datetime dtype before arithmetic to avoid Timestamp - float TypeError
    sku_metrics["last_sale_date"] = pd.to_datetime(sku_metrics.get("last_sale_date"), errors="coerce")
    sku_metrics["last_order_date"] = pd.to_datetime(sku_metrics.get("last_order_date"), errors="coerce")
    sku_metrics["last_sale_date"] = sku_metrics["last_sale_date"].fillna(sku_metrics["last_order_date"])
    sku_metrics["days_since_last_sale"] = (today - sku_metrics["last_sale_date"]).dt.days
    sku_metrics["days_since_last_sale"] = sku_metrics["days_since_last_sale"].fillna(config.default_date_months * 30)

    period_days = _compute_period_days(sales_orders, config.default_date_months * 30)

    sku_metrics["days_of_inventory"] = np.where(
        sku_metrics["avg_daily_sales_sy"] > 0,
        sku_metrics["inventory_sy"] / sku_metrics["avg_daily_sales_sy"],
        float("inf"),
    )

    sku_metrics["stock_turn"] = np.where(
        sku_metrics["inventory_sy"] > 0,
        (sku_metrics["quantity_sy"] * (365 / period_days)) / np.maximum(sku_metrics["inventory_sy"], 1e-6),
        0.0,
    )

    sku_metrics = assign_sku_ratings(
        sku_metrics.reset_index(),
        "orders_count",
        count_column="orders_count",
    )
    sku_metrics.set_index("sku", inplace=True)
    tmark("assign_sku_ratings")

    nominal_lead = _merge_lead_time(items, product_lines)
    sku_metrics = sku_metrics.join(nominal_lead.rename("nominal_lead_time_days"), how="left")

    actual_lead = _actual_lead_time_from_receipts(purchase_orders, receipts)
    sku_metrics = sku_metrics.join(actual_lead, how="left")
    tmark("compute_lead_times")

    # Lead time selection:
    # Previous behavior: use actual lead time when available, else nominal, fallback 33.
    # New requirement: only use actual if it is strictly greater than the nominal value.
    # Rationale: avoid understating lead time due to early/partial receipts that shorten the median actual.
    actual = pd.to_numeric(sku_metrics.get("actual_lead_time_days"), errors="coerce")
    nominal = pd.to_numeric(sku_metrics.get("nominal_lead_time_days"), errors="coerce")

    # If nominal is missing or non-positive, fall back to actual.
    # Otherwise take nominal unless actual > nominal.
    chosen = nominal.copy()
    # Where nominal is NaN or <=0, use actual
    mask_nominal_bad = nominal.isna() | (nominal <= 0)
    chosen.loc[mask_nominal_bad] = actual.loc[mask_nominal_bad]
    # Where actual is valid (>0) and greater than nominal, upgrade to actual
    mask_use_actual = (~mask_nominal_bad) & actual.notna() & (actual > nominal) & (actual > 0)
    chosen.loc[mask_use_actual] = actual.loc[mask_use_actual]

    # Fallback default 33 for any remaining missing/non-positive
    chosen = chosen.where(chosen > 0, 33)
    sku_metrics["lead_time_days"] = chosen

    # Compute cost-center seasonality (last 12 months ending at end date)
    seasonality = _compute_monthly_seasonality_user(cost_centers)
    # Precompute window multipliers for unique (cost_center, lead_time)
    today_d = date.today()
    # Map for quick lookup
    window_multiplier_cache: Dict[Tuple[str, int], float] = {}
    def _get_multiplier(cc: Optional[str], lt_days: float) -> float:
        cc_key = str(cc) if cc is not None and str(cc) in seasonality else (list(seasonality.keys())[0] if seasonality else "__default__")
        days_int = int(max(round(pd.to_numeric(pd.Series([lt_days]), errors="coerce").fillna(0).iloc[0]), 0))
        key = (cc_key, days_int)
        if key in window_multiplier_cache:
            return window_multiplier_cache[key]
        month_pct = seasonality.get(cc_key)
        mult = _seasonal_window_multiplier(month_pct, today_d, days_int)
        window_multiplier_cache[key] = mult
        return mult

    # Original flat cover for reference
    sku_metrics["cover_required_flat_sy"] = sku_metrics["avg_daily_sales_sy"] * sku_metrics["lead_time_days"]
    # Seasonally adjusted cover over the lead-time horizon
    # cover_seasonal = avg_daily * seasonal_window_multiplier
    if "cost_center" not in sku_metrics.columns:
        sku_metrics["cost_center"] = list(items_base.set_index("sku").get("cost_center", pd.Series(dtype=object)).reindex(sku_metrics.index))
    multipliers = [
        _get_multiplier(row.get("cost_center"), row.get("lead_time_days"))
        for _, row in sku_metrics.reset_index().iterrows()
    ]
    sku_metrics = sku_metrics.reset_index()
    sku_metrics["seasonal_window_multiplier"] = pd.to_numeric(pd.Series(multipliers), errors="coerce").fillna(0.0)
    sku_metrics.set_index("sku", inplace=True)
    sku_metrics["cover_required_sy"] = sku_metrics["avg_daily_sales_sy"] * sku_metrics["seasonal_window_multiplier"]
    # Net inventory for runout uses on-order plus assumed partial receipts
    sku_metrics["net_inventory_sy"] = sku_metrics["inventory_sy"] + (sku_metrics["on_order_sy"] + sku_metrics.get("partial_received_po", 0.0))
    sku_metrics["runout_risk"] = sku_metrics["net_inventory_sy"] < sku_metrics["cover_required_sy"]

    # Integrate JSTOCK policy for new launches (< 6 months):
    # Use JSTOCK (if > 0) as the target on hand instead of seasonal cover when the launch age is < 6 months,
    # unless recent history suggests ordering more than JSTOCK (i.e., seasonal cover > JSTOCK).
    # Steps:
    #  - Join JSTOCK per SKU
    #  - Compute per-price-class launch date and per-SKU launch age in months
    #  - Compute effective target_on_hand = max(cover_required_sy, jstock) when launch_age_months < 6 and jstock > 0; else cover_required_sy
    #  - Recompute runout risk and reorder quantities from this target
    # Map ITEMSTK SKU to base_sku and take the maximum JSTOCK per base_sku, then join
    js_series = pd.Series(dtype=float)
    try:
        if not itemstks.empty:
            js = itemstks.copy()
            js["sku"] = js["sku"].astype(str)
            # Build full mapping sku->base_sku from items (covers aliases)
            if not items.empty and "base_sku" in items.columns:
                full_map = dict(zip(items["sku"].astype(str), items["base_sku"].astype(str)))
                js["sku"] = js["sku"].map(lambda x: full_map.get(x, x))
            # Aggregate to max JSTOCK per base sku
            js = js.groupby("sku", as_index=False)["jstock"].max()
            js_series = js.set_index("sku")["jstock"]
    except Exception:
        pass
    sku_metrics = sku_metrics.join(js_series.rename("jstock"), how="left")
    sku_metrics["jstock"] = pd.to_numeric(sku_metrics.get("jstock"), errors="coerce").fillna(0.0)

    # Ensure price_class is available for all SKUs by joining from global items map (base_sku -> price_class)
    if 'price_class' not in sku_metrics.columns or sku_metrics['price_class'].isna().any():
        try:
            if not items_all_base.empty and 'price_class' in items_all_base.columns:
                pc_global = items_all_base.set_index('base_sku')['price_class']
                sku_metrics = sku_metrics.join(pc_global.rename('price_class'), how='left')
        except Exception:
            pass

    # Build launch mapping from the actual set of price classes present in sku_metrics
    pcs_for_launch = sku_metrics.get('price_class') if 'price_class' in sku_metrics.columns else None
    launch_map = get_launch_mapping(pcs_for_launch)
    def _sku_launch_date(pc):
        dt = launch_map.get(str(pc))
        return pd.Timestamp(dt) if dt else pd.NaT
    sku_metrics["launch_date_pc"] = sku_metrics.get("price_class").map(_sku_launch_date)
    today_ts = pd.Timestamp(date.today())
    sku_metrics["launch_age_days"] = (today_ts - pd.to_datetime(sku_metrics["launch_date_pc"], errors='coerce')).dt.days
    sku_metrics["launch_age_months"] = (sku_metrics["launch_age_days"] / 30.44).fillna(np.inf)

    # Effective target_on_hand per SKU
    cover = pd.to_numeric(sku_metrics.get("cover_required_sy"), errors="coerce").fillna(0.0)
    jstk = pd.to_numeric(sku_metrics.get("jstock"), errors="coerce").fillna(0.0)
    young = pd.to_numeric(sku_metrics.get("launch_age_months"), errors="coerce").fillna(np.inf) < 6.0
    # If young and jstock>0: target = maximum of seasonal cover and jstock; else target = seasonal cover
    eff_target = cover.copy()
    mask_use_jstock = young & (jstk > 0)
    eff_target.loc[mask_use_jstock] = np.maximum(cover.loc[mask_use_jstock], jstk.loc[mask_use_jstock])
    sku_metrics["target_on_hand_sy"] = eff_target

    # Recompute runout and reorder from effective target
    sku_metrics["net_inventory_sy"] = pd.to_numeric(sku_metrics.get("net_inventory_sy"), errors="coerce").fillna(0.0)
    sku_metrics["runout_risk"] = sku_metrics["net_inventory_sy"] < sku_metrics["target_on_hand_sy"]
    safety_cover = pd.to_numeric(sku_metrics.get("avg_daily_sales_sy"), errors="coerce").fillna(0.0) * 7
    # Include total backordered quantity (SY) in reorder recommendation
    # Ensure column exists even if no backorders this period
    if "backorder_qty_sy" not in sku_metrics.columns:
        sku_metrics["backorder_qty_sy"] = 0.0
    backorder_qty = pd.to_numeric(sku_metrics.get("backorder_qty_sy"), errors="coerce").fillna(0.0)
    base_reorder = np.maximum(
        sku_metrics["target_on_hand_sy"] + safety_cover - sku_metrics["net_inventory_sy"],
        0,
    )
    sku_metrics["reorder_qty_sy"] = base_reorder + backorder_qty

    sku_metrics.reset_index(inplace=True)
    # Deduplicate any accidental duplicates by SKU with value-preserving aggregation
    if not sku_metrics.empty:
        # Build aggregation map: sum for inventories/orders, max for rates/covers, first for labels
        agg = {}
        for col in sku_metrics.columns:
            if col == "sku":
                continue
            if col in {"inventory_sy", "on_order_sy", "quantity_sy", "orders_count", "backorder_count", "net_inventory_sy", "partial_received_po", "backorder_qty_sy"}:
                agg[col] = "sum"
            elif pd.api.types.is_numeric_dtype(sku_metrics[col]):
                agg[col] = "max"
            else:
                agg[col] = "first"
        sku_metrics = sku_metrics.groupby("sku", as_index=False).agg(agg)
    # Recompute derived fields that depend on aggregated sums
    sku_metrics["assumed_on_order_sy"] = (
        pd.to_numeric(sku_metrics.get("on_order_sy"), errors="coerce").fillna(0.0)
        + pd.to_numeric(sku_metrics.get("partial_received_po"), errors="coerce").fillna(0.0)
    )
    sku_metrics["net_inventory_sy"] = pd.to_numeric(sku_metrics.get("inventory_sy"), errors="coerce").fillna(0.0) + sku_metrics["assumed_on_order_sy"]
    # Re-evaluate days_of_inventory and stock_turn on the aggregated values
    avg_daily = pd.to_numeric(sku_metrics.get("avg_daily_sales_sy"), errors="coerce").fillna(0)
    inv = pd.to_numeric(sku_metrics.get("inventory_sy"), errors="coerce").fillna(0)
    period_days = _compute_period_days(sales_orders, get_config().default_date_months * 30)
    sku_metrics["days_of_inventory"] = np.where(avg_daily > 0, inv / avg_daily, float("inf"))
    qty_total = pd.to_numeric(sku_metrics.get("quantity_sy"), errors="coerce").fillna(0)
    sku_metrics["stock_turn"] = np.where(inv > 0, (qty_total * (365 / period_days)) / np.maximum(inv, 1e-6), 0.0)
    # Do not filter out SKUs not present in items; keep any SKU that appears in sales/rolls/POs
    tmark("coverage_reorder")

    # --- Exclude dropped / non-replenishable items from Overview and Stock Turn ---
    # Criteria:
    #   1) ITEM.IPOL1, IPOL2, or IPOL3 = 'DI'  (dropped-item policy flag)
    #   2) ITEMSTK.JFILL2 = 'N'                 (excluded from replenishment)
    try:
        excluded_skus: set = set()
        # IPOL1/2/3 = 'DI' — use base_sku so alias items are also excluded
        if not items.empty:
            base_col = "base_sku" if "base_sku" in items.columns else "sku"
            for pol_col in ["ipol1", "ipol2", "ipol3"]:
                if pol_col in items.columns:
                    pol_vals = items[pol_col].fillna("").astype(str).str.strip().str.upper()
                    excluded_skus |= set(items.loc[pol_vals == "DI", base_col].astype(str))
        # JFILL2 = 'N' — map raw item SKU → base_sku via alias map
        if not itemstks.empty and "jfill2" in itemstks.columns:
            jfill2_vals = itemstks["jfill2"].fillna("").astype(str).str.strip().str.upper()
            raw_jfill2_excluded = set(itemstks.loc[jfill2_vals == "N", "sku"].astype(str))
            if raw_jfill2_excluded and not items.empty and "sku" in items.columns and "base_sku" in items.columns:
                sku_to_base = dict(zip(items["sku"].astype(str), items["base_sku"].astype(str)))
                excluded_skus |= {sku_to_base.get(s, s) for s in raw_jfill2_excluded}
            else:
                excluded_skus |= raw_jfill2_excluded
        if excluded_skus and not sku_metrics.empty and "sku" in sku_metrics.columns:
            sku_metrics = sku_metrics.loc[~sku_metrics["sku"].astype(str).isin(excluded_skus)].copy()
    except Exception:
        pass  # Never let exclusion logic break the dashboard
    tmark("di_jfill2_exclusion")

    summary = _compute_summary_metrics(sku_metrics)
    # Determine stock turn target: use per-CC target if all SKUs share a single CC with a saved target; else default
    stock_turn_target = config.stockturn_target
    try:
        if not sku_metrics.empty and "cost_center" in sku_metrics.columns:
            ccs = sku_metrics["cost_center"].dropna().astype(str).unique().tolist()
            if len(ccs) == 1:
                cc_target = get_target_for_cc(ccs[0])
                if cc_target is not None:
                    stock_turn_target = float(cc_target)
    except Exception:
        pass
    summary["stock_turn_target"] = stock_turn_target
    tmark("summary")

    # Persist a snapshot for time-series charts (best-effort) for current filter
    try:
        total_avg_daily = float(pd.to_numeric(sku_metrics.get("avg_daily_sales_sy"), errors="coerce").fillna(0).sum())
        total_inventory = float(pd.to_numeric(sku_metrics.get("inventory_sy"), errors="coerce").fillna(0).sum())
        total_orders = float(pd.to_numeric(sku_metrics.get("orders_count"), errors="coerce").fillna(0).sum())
        total_backorders = float(pd.to_numeric(sku_metrics.get("backorder_count"), errors="coerce").fillna(0).sum())
        stock_turn = (total_avg_daily * 365.0) / total_inventory if total_inventory > 0 else 0.0
        fill_rate = (1 - (total_backorders / total_orders)) if total_orders > 0 else 0.0
        append_metrics_snapshot(
            cost_centers=cost_centers,
            start_date=start,
            end_date=end,
            stock_turn=stock_turn,
            fill_rate=fill_rate,
            total_orders=total_orders,
            total_backorders=total_backorders,
            total_inventory_sy=total_inventory,
            total_avg_daily_sy=total_avg_daily,
        )
    except Exception:
        pass
    tmark("snapshot_persist")

    # Note: per-cost-center snapshot warm-up is handled from the UI to avoid recursion

    qty_sy_series = pd.to_numeric(_safe_series(sales_orders, "quantity_sy"), errors="coerce").fillna(0)
    mask_backorder = sales_orders["backorder_flag"] & (qty_sy_series > 0)
    # Diagnostics: track suspicious rows we excluded
    try:
        neg_qty_count = int((qty_sy_series < 0).sum())
        detail_series_dbg = _safe_series(sales_orders, "detail_line_status", dtype=object)
        non_rb_count = int(~detail_series_dbg.fillna("").astype(str).str.strip().str.upper().isin(["R", "B"]).sum())
        timings.append(("excluded_neg_qty_rows", float(neg_qty_count)))
        timings.append(("excluded_non_RB_rows", float(non_rb_count)))
    except Exception:
        pass
    # Use all-accounts source to include account_number == 1 for history
    qty_sy_series_all_hist = pd.to_numeric(_safe_series(so_all_accounts, "quantity_sy"), errors="coerce").fillna(0)
    mask_backorder_hist = so_all_accounts["backorder_flag"] & (qty_sy_series_all_hist > 0)
    backorders = so_all_accounts.loc[mask_backorder_hist].copy()
    # Ensure required columns exist even if upstream frames were empty/minimal
    _bo_required = {
        "sku": object,
        "order_number": object,
        "line_number": object,
        "order_entry_date": "datetime64[ns]",
        "quantity_sy": "float64",
        "detail_line_status": object,
    }
    for _col, _dtype in _bo_required.items():
        if _col not in backorders.columns:
            backorders[_col] = pd.Series(index=backorders.index, dtype=_dtype)
    backorders = backorders[[
        "sku",
        "order_number",
        "line_number",
        "order_entry_date",
        "quantity_sy",
        "detail_line_status",
    ]]

    # backorder_qty_sy joined earlier; nothing to do here

    backorder_history = backorder_store.update_history(backorders)
    tmark("backorder_history")

    timings_dict: Dict[str, float] = {name: float(sec) for name, sec in timings}
    timings_dict["total"] = float(sum(sec for _, sec in timings))

    return {
        "summary": summary,
        "sku_metrics": sku_metrics,
        "backorders": backorders,
        "backorder_history": backorder_history,
        "sales_orders": sales_orders,
        "purchase_orders": purchase_orders,
        "inventory": rolls,
        "items": items,
        "timings": timings_dict,
    }
