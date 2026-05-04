from __future__ import annotations

from pathlib import Path
import os
from typing import Tuple

import pandas as pd

# Persist to a user-writable location (supports packaged EXE)
def _user_history_dir() -> Path:
    """Resolve a user-writable history directory.

    Prefer %APPDATA%/PurchaseOrderBot/history on Windows, fallback to Home.
    """
    try:
        base = Path(os.environ.get("APPDATA", "")).expanduser()
        if str(base).strip():
            return base / "PurchaseOrderBot" / "history"
    except Exception:
        pass
    return Path.home() / "PurchaseOrderBot" / "history"


# User-scoped backorder history path
_USER_BACKORDER_FILE = _user_history_dir() / "backorder_history.csv"

# Legacy seed file bundled with the app source (read-only in packaged EXE)
_SEED_BACKORDER_FILE = Path(__file__).resolve().parent / "backorder_history.csv"

_BACKORDER_COLUMNS = [
    "order_number",
    "line_number",
    "sku",
    "order_entry_date",
    "quantity_sy",
    "detail_line_status",
    "first_detected_at",
    "last_seen_at",
    "resolved_at",
    "is_active",
]


def _ensure_dataframe(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=_BACKORDER_COLUMNS)
    missing = [col for col in _BACKORDER_COLUMNS if col not in df.columns]
    for col in missing:
        df[col] = pd.NaT if "_at" in col else (False if col == "is_active" else pd.NA)
    return df[_BACKORDER_COLUMNS].copy()


def load_history() -> pd.DataFrame:
    """Return the locally persisted backorder history.

    Tries user-writable history first; if missing, attempts to load a bundled seed file.
    """

    path_to_read: Path | None = None
    if _USER_BACKORDER_FILE.exists():
        path_to_read = _USER_BACKORDER_FILE
    elif _SEED_BACKORDER_FILE.exists():
        path_to_read = _SEED_BACKORDER_FILE
    else:
        return _ensure_dataframe(None)

    df = pd.read_csv(
        path_to_read,
        parse_dates=["order_entry_date", "first_detected_at", "last_seen_at", "resolved_at"],
        dtype={"order_number": str, "line_number": str, "sku": str, "detail_line_status": str},
    )
    df = _ensure_dataframe(df)
    # Purge invalid legacy rows: require positive qty and strict R/B status
    qty_ok = pd.to_numeric(df.get("quantity_sy"), errors="coerce").fillna(0) > 0
    status = df.get("detail_line_status", "").fillna("").astype(str).str.strip().str.upper()
    status_ok = status.isin(["R", "B"])
    df = df.loc[qty_ok & status_ok].copy()
    return df


def _serialize_history(df: pd.DataFrame) -> None:
    """Persist history to the user-writable file; swallow IO errors to avoid crashing UI."""
    try:
        target = _USER_BACKORDER_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        df_to_save = df.copy()
        df_to_save.to_csv(target, index=False)
    except Exception:
        # Best-effort only; do not propagate in UI context
        pass


def _normalize_backorders(backorders: pd.DataFrame) -> pd.DataFrame:
    if backorders.empty:
        return pd.DataFrame(columns=["order_number", "sku"])

    normalized = backorders.copy()
    normalized["order_number"] = normalized["order_number"].astype(str)
    if "line_number" in normalized.columns:
        normalized["line_number"] = normalized["line_number"].fillna("").astype(str)
    else:
        normalized["line_number"] = ""
    normalized["sku"] = normalized["sku"].astype(str)
    if "order_entry_date" in normalized.columns:
        normalized["order_entry_date"] = pd.to_datetime(normalized["order_entry_date"], errors="coerce")
    else:
        normalized["order_entry_date"] = pd.NaT

    if "quantity_sy" in normalized.columns:
        normalized["quantity_sy"] = pd.to_numeric(normalized["quantity_sy"], errors="coerce")
    else:
        normalized["quantity_sy"] = pd.NA

    normalized["detail_line_status"] = normalized.get("detail_line_status", pd.Series(index=normalized.index)).astype(str)
    return normalized[["order_number", "line_number", "sku", "order_entry_date", "quantity_sy", "detail_line_status"]]


def update_history(backorders: pd.DataFrame) -> pd.DataFrame:
    """Upsert the provided backorders into the local history and return the updated frame."""

    current = load_history()
    normalized_backorders = _normalize_backorders(backorders)

    now = pd.Timestamp.utcnow()

    if current.empty:
        current = _ensure_dataframe(None)

    key_cols = ["order_number", "line_number", "sku"]

    if not normalized_backorders.empty:
        normalized_backorders = normalized_backorders.drop_duplicates(subset=key_cols)
        normalized_backorders.set_index(key_cols, inplace=True)

        current = current.set_index(key_cols)
        if current.empty:
            current = normalized_backorders.copy()
            current["first_detected_at"] = now
            current["last_seen_at"] = now
            current["resolved_at"] = pd.NaT
            current["is_active"] = True
        else:
            # Update existing rows
            overlap = normalized_backorders.index.intersection(current.index)
            if len(overlap) > 0:
                current.loc[overlap, "order_entry_date"] = normalized_backorders.loc[overlap, "order_entry_date"]
                current.loc[overlap, "quantity_sy"] = normalized_backorders.loc[overlap, "quantity_sy"]
                current.loc[overlap, "detail_line_status"] = normalized_backorders.loc[overlap, "detail_line_status"]
                current.loc[overlap, "last_seen_at"] = now
                current.loc[overlap, "resolved_at"] = pd.NaT
                current.loc[overlap, "is_active"] = True

            # Insert new rows
            new_index = normalized_backorders.index.difference(current.index)
            if len(new_index) > 0:
                additions = normalized_backorders.loc[new_index]
                additions["first_detected_at"] = now
                additions["last_seen_at"] = now
                additions["resolved_at"] = pd.NaT
                additions["is_active"] = True
                current = pd.concat([current, additions])

        current.reset_index(inplace=True)
        normalized_backorders.reset_index(inplace=True)
    else:
        current = current.reset_index() if isinstance(current.index, pd.MultiIndex) else current

    # Resolve entries no longer present
    if not normalized_backorders.empty:
        active_keys = set(map(tuple, normalized_backorders[key_cols].values.tolist()))
    else:
        active_keys = set()

    def _mark_resolved(row):
        # Include line_number in key to avoid collapsing distinct lines
        key = (row["order_number"], row["line_number"], row["sku"])
        if key not in active_keys and row.get("is_active", False):
            row["is_active"] = False
            if pd.isna(row.get("resolved_at")):
                row["resolved_at"] = now
        elif key in active_keys:
            row["is_active"] = True
        return row

    current = current.apply(_mark_resolved, axis=1)

    current = _ensure_dataframe(current)
    _serialize_history(current)
    return current
