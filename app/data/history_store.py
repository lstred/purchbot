from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Dict, Optional
import os
import shutil

import pandas as pd


def _user_history_dir() -> Path:
    """Resolve a user-writable history directory (supports packaged EXE).

    Prefer %APPDATA%/PurchaseOrderBot/history on Windows, fallback to Home.
    """
    try:
        base = Path(os.environ.get("APPDATA", "")).expanduser()
        if str(base).strip():
            return base / "PurchaseOrderBot" / "history"
    except Exception:
        pass
    return Path.home() / "PurchaseOrderBot" / "history"


HISTORY_DIR = _user_history_dir()
HISTORY_FILE = HISTORY_DIR / "metrics_history.csv"


def _legacy_history_file() -> Path:
    """Locate legacy history path relative to project root (source runs)."""
    return Path(__file__).resolve().parent.parent.parent / "history" / "metrics_history.csv"


def _ensure_history_dir() -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    # Best-effort migration of legacy history if present and new file missing
    try:
        legacy = _legacy_history_file()
        if legacy.exists() and not HISTORY_FILE.exists():
            HISTORY_FILE.write_bytes(legacy.read_bytes())
    except Exception:
        # Ignore migration issues; history is best-effort
        pass


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def append_metrics_snapshot(
    *,
    cost_centers: list[str],
    start_date: Optional[date],
    end_date: Optional[date],
    stock_turn: float,
    fill_rate: float,
    total_orders: float,
    total_backorders: float,
    total_inventory_sy: float,
    total_avg_daily_sy: float,
) -> None:
    """Append or upsert a metrics snapshot for the current day and filter set.

    Upsert key: (day, cost_centers_sorted, start_date, end_date).
    """
    _ensure_history_dir()
    cc_key = ",".join(sorted([str(c) for c in (cost_centers or [])]))
    ts = _now_utc()
    day = ts.date().isoformat()
    row: Dict[str, object] = {
        "timestamp": ts.isoformat(),
        "day": day,
        "cost_centers": cc_key,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "stock_turn": float(stock_turn or 0.0),
        "fill_rate": float(fill_rate or 0.0),
        "total_orders": float(total_orders or 0.0),
        "total_backorders": float(total_backorders or 0.0),
        "total_inventory_sy": float(total_inventory_sy or 0.0),
        "total_avg_daily_sy": float(total_avg_daily_sy or 0.0),
    }

    try:
        if HISTORY_FILE.exists():
            df = pd.read_csv(HISTORY_FILE)
        else:
            df = pd.DataFrame()
        # Upsert by key
        mask = (
            (df.get("day") == row["day"]) &
            (df.get("cost_centers") == row["cost_centers"]) &
            (df.get("start_date") == row["start_date"]) &
            (df.get("end_date") == row["end_date"]) 
        ) if not df.empty else pd.Series(dtype=bool)

        if not df.empty and mask.any():
            df.loc[mask, list(row.keys())] = row  # type: ignore[index]
        else:
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)

        df.to_csv(HISTORY_FILE, index=False)
    except Exception:
        # Swallow errors to avoid breaking the dashboard; history is best-effort
        pass


def load_metrics_history(
    *, cost_centers: list[str], start_date: Optional[date], end_date: Optional[date]
) -> pd.DataFrame:
    """Load persisted history filtered by cost centers and optional date window key.

    Filtering by exact cost center set (sorted, joined) so time series reflects the same scope.
    """
    try:
        if not HISTORY_FILE.exists():
            return pd.DataFrame(columns=[
                "timestamp","day","cost_centers","start_date","end_date",
                "stock_turn","fill_rate","total_orders","total_backorders",
                "total_inventory_sy","total_avg_daily_sy"
            ])
        df = pd.read_csv(HISTORY_FILE)
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
        df["day"] = pd.to_datetime(df["day"], errors="coerce")
        cc_key = ",".join(sorted([str(c) for c in (cost_centers or [])]))
        df = df[df.get("cost_centers") == cc_key].copy()
        # If the user changes the analysis window definition, keep series scoped to the same window keys
        key_start = start_date.isoformat() if start_date else None
        key_end = end_date.isoformat() if end_date else None
        df = df[(df.get("start_date") == key_start) & (df.get("end_date") == key_end)]
        return df.sort_values("day")
    except Exception:
        return pd.DataFrame()
