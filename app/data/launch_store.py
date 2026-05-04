from __future__ import annotations

from pathlib import Path
import os
import json
from datetime import date, datetime
from typing import Dict, Optional

import pandas as pd

_LAUNCH_FLOOR = date(2025, 8, 4)


def _launch_file_path() -> Path:
    try:
        base_dir = Path(os.environ.get("APPDATA", Path.home())) / "PurchaseOrderBot" / "config"
    except Exception:
        base_dir = Path.home() / "PurchaseOrderBot" / "config"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / "price_class_launch_dates.json"


def _to_date(obj) -> Optional[date]:
    if obj is None:
        return None
    if isinstance(obj, date) and not isinstance(obj, datetime):
        return obj
    try:
        ts = pd.to_datetime(obj, errors="coerce")
        if pd.isna(ts):
            return None
        return ts.date()
    except Exception:
        return None


def load_launch_dates() -> Dict[str, str]:
    path = _launch_file_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_launch_dates(mapping: Dict[str, str]) -> bool:
    try:
        _launch_file_path().write_text(json.dumps(mapping, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def get_launch_date(price_class: str) -> Optional[date]:
    raw = load_launch_dates().get(str(price_class))
    return _to_date(raw)


def set_launch_date_if_missing(price_class: str, launch_dt: date) -> bool:
    """Set launch date for a price class if not already set. Apply floor of 2025-08-04.
    Returns True if file saved, False otherwise.
    """
    existing = load_launch_dates()
    key = str(price_class)
    if key in existing:
        return True
    # Apply floor
    floor_dt = max(launch_dt, _LAUNCH_FLOOR)
    existing[key] = floor_dt.isoformat()
    return save_launch_dates(existing)


def compute_min_receive_by_price_class(items: pd.DataFrame, rolls: pd.DataFrame) -> Dict[str, date]:
    if items is None or items.empty or rolls is None or rolls.empty:
        return {}
    cols_needed = {"sku", "price_class"}
    if not cols_needed.issubset(set(items.columns)):
        return {}
    r = rolls[[c for c in ["sku", "receive_date"] if c in rolls.columns]].copy()
    if r.empty:
        return {}
    r["receive_date"] = pd.to_datetime(r.get("receive_date"), errors="coerce")
    r = r.dropna(subset=["receive_date"])  # keep only valid dates
    if r.empty:
        return {}
    merged = r.merge(items[["sku", "price_class"]], on="sku", how="inner")
    if merged.empty:
        return {}
    min_by_pc = merged.groupby("price_class")["receive_date"].min()
    out: Dict[str, date] = {str(pc): dt.date() for pc, dt in min_by_pc.items() if pd.notna(dt)}
    return out


def update_launch_dates_from_rolls(items: pd.DataFrame, rolls: pd.DataFrame) -> int:
    """Populate missing launch dates using oldest receive date per price class (with floor).
    Does not overwrite existing entries. Returns count of price classes newly written.
    """
    candidates = compute_min_receive_by_price_class(items, rolls)
    if not candidates:
        return 0
    existing = load_launch_dates()
    new_count = 0
    for pc, dt in candidates.items():
        if pc in existing:
            continue
        # Floor
        floored = max(dt, _LAUNCH_FLOOR)
        existing[pc] = floored.isoformat()
        new_count += 1
    if new_count:
        save_launch_dates(existing)
    return new_count


def get_launch_mapping(price_classes: Optional[pd.Series]) -> Dict[str, date]:
    """Return mapping price_class -> date for provided list/series; missing map to floor date.
    (We won't auto-save here; use update_launch_dates_from_rolls to seed.)
    """
    raw = load_launch_dates()
    mapping: Dict[str, date] = {}
    if price_classes is None:
        return mapping
    for pc in price_classes.dropna().astype(str).unique().tolist():
        dt = _to_date(raw.get(pc))
        if dt is None:
            dt = _LAUNCH_FLOOR
        mapping[pc] = dt
    return mapping
