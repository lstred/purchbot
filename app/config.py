from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import importlib
import os
from typing import List, Optional
from pathlib import Path
import json


@dataclass(slots=True)
class AppConfig:
    """Container for application level configuration."""

    connection_string: str
    stockturn_target: float = 4.0
    default_cost_centers: List[str] = field(default_factory=lambda: ["010"])
    default_date_months: int = 18  # default historical window for demand calculations
    rating_buckets: tuple[float, float, float] = (0.25, 0.5, 0.75)
    cache_ttl_seconds: int = 6 * 60  # refresh cached queries every 6 minutes by default


def _load_local_connection_string() -> Optional[str]:
    """Attempt to load SQL Server connection string from config_local module."""

    module_name = "config_local"
    if module_name in os.environ.get("PYTHONPATH", ""):
        importlib.invalidate_caches()

    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        return None

    return getattr(module, "SQLSERVER_ODBC", None)


def _load_user_connection_string() -> Optional[str]:
    """Load SQL Server connection from a user-writable config in AppData.

    Looks for %APPDATA%/PurchaseOrderBot/config.json with key "SQLSERVER_ODBC".
    Returns None if not found or unreadable.
    """
    try:
        base = Path(os.environ.get("APPDATA", "")).expanduser()
        cfg_dir = (base if str(base).strip() else Path.home()) / "PurchaseOrderBot"
        cfg_file = cfg_dir / "config.json"
        if cfg_file.exists():
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
            val = data.get("SQLSERVER_ODBC")
            return str(val) if val else None
    except Exception:
        return None
    return None

SQLSERVER_ODBC = (
    "Driver={ODBC Driver 18 for SQL Server};"
    "Server=NRFVMSSQL04;"
    "Database=NRF_REPORTS;"
    "Trusted_Connection=Yes;"
    "Encrypt=no;"
)




@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """Return the cached application configuration."""

    connection_string = (
        os.environ.get("SQLSERVER_ODBC")
        or _load_user_connection_string()
        or _load_local_connection_string()
    )
    if not connection_string:
        raise RuntimeError(
            "No SQL Server connection string configured. Set the SQLSERVER_ODBC env var or "
            "create a config_local.py file alongside the project (see config_local.sample.py)."
        )

    return AppConfig(connection_string=connection_string)
