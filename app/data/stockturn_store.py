from __future__ import annotations

from pathlib import Path
import os
import json
from typing import Dict, Optional


def _targets_file_path() -> Path:
    try:
        base_dir = Path(os.environ.get("APPDATA", Path.home())) / "PurchaseOrderBot" / "config"
    except Exception:
        base_dir = Path.home() / "PurchaseOrderBot" / "config"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / "stockturn_targets.json"


def load_targets() -> Dict[str, float]:
    path = _targets_file_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cleaned: Dict[str, float] = {}
        for k, v in (data or {}).items():
            try:
                cleaned[str(k)] = float(v)
            except Exception:
                continue
        return cleaned
    except Exception:
        return {}


def save_target(cost_center: str, target: float) -> bool:
    data = load_targets()
    try:
        data[str(cost_center)] = float(target)
    except Exception:
        return False
    try:
        _targets_file_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def get_target_for_cc(cost_center: str) -> Optional[float]:
    try:
        return float(load_targets().get(str(cost_center)))
    except Exception:
        return None
