from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Dict, Iterable
from urllib.parse import quote_plus

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def _create_engine(connection_string: str) -> Engine:
    """Create a SQLAlchemy engine for the provided ODBC connection string."""

    odbc_url = f"mssql+pyodbc:///?odbc_connect={quote_plus(connection_string)}"
    return create_engine(odbc_url, fast_executemany=True, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_engine(connection_string: str) -> Engine:
    """Return a cached SQLAlchemy engine bound to the connection string."""

    return _create_engine(connection_string)


@contextmanager
def get_connection(connection_string: str):
    """Context manager yielding an open DBAPI connection."""

    engine = get_engine(connection_string)
    with engine.connect() as conn:
        yield conn


def validate_connection(connection_string: str) -> bool:
    """Return True if the database can be reached."""

    try:
        with get_connection(connection_string) as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - defensive, depends on environment
        raise ConnectionError("Failed to connect to SQL Server") from exc
    return True


def read_dataframe(connection_string: str, sql: str, params: Dict[str, Any] | None = None) -> pd.DataFrame:
    """Execute a SQL query and return the results as a pandas DataFrame."""

    with get_connection(connection_string) as conn:
        return pd.read_sql_query(text(sql), conn, params=params)


def execute_many(connection_string: str, sql: str, rows: Iterable[Dict[str, Any]]):
    """Execute a parameterized statement against many rows."""

    with get_connection(connection_string) as conn:
        conn.execute(text(sql), list(rows))
