from __future__ import annotations

from pathlib import Path
import os
import json
from typing import Dict, List, Optional

import pandas as pd


def _seasonality_file_path() -> Path:
    try:
        base_dir = Path(os.environ.get("APPDATA", Path.home())) / "PurchaseOrderBot" / "config"
    except Exception:
        base_dir = Path.home() / "PurchaseOrderBot" / "config"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / "seasonality.json"


def load_seasonality() -> Dict[str, List[float]]:
    path = _seasonality_file_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Validate structure: dict[str, list[float]] with 12 elements each
        cleaned: Dict[str, List[float]] = {}
        for k, v in data.items():
            if isinstance(v, list) and len(v) == 12:
                try:
                    vals = [float(x) for x in v]
                    cleaned[str(k)] = vals
                except Exception:
                    continue
        return cleaned
    except Exception:
        return {}


def save_seasonality(mapping: Dict[str, List[float]]) -> bool:
    # Ensure valid shape and normalize each list to sum to 1.0 (if possible)
    out: Dict[str, List[float]] = {}
    for k, v in (mapping or {}).items():
        if not isinstance(v, list) or len(v) != 12:
            continue
        try:
            floats = [max(float(x), 0.0) for x in v]
        except Exception:
            continue
        s = sum(floats)
        if s > 0:
            floats = [x / s for x in floats]
        else:
            floats = [1.0 / 12.0] * 12
        out[str(k)] = floats
    try:
        _seasonality_file_path().write_text(json.dumps(out, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def get_for_cost_center(cost_center: Optional[str]) -> pd.Series:
    data = load_seasonality()
    key = str(cost_center) if cost_center is not None and str(cost_center) in data else None
    vals = data.get(key) if key is not None else None
    if not vals:
        vals = [1.0 / 12.0] * 12
    # Series indexed 1..12
    return pd.Series({i + 1: float(vals[i]) for i in range(12)})


def save_for_cost_center(cost_center: str, values: List[float]) -> bool:
    data = load_seasonality()
    data[str(cost_center)] = list(values)
    return save_seasonality(data)
