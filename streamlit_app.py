from pathlib import Path
import os
import json
import streamlit as st

from app.config import get_config
from app.ui import dashboard

# IMPORTANT: Configure the page BEFORE any UI is rendered anywhere.
# Doing this at module import time in the main script ensures the
# frontend receives SessionInfo first and avoids the transient
# "Bad message format" toast on first load.
st.set_page_config(page_title="Inventory Dashboard", layout="wide")


def _user_config_path() -> Path:
    base = Path(os.environ.get("APPDATA", "")).expanduser()
    cfg_dir = (base if str(base).strip() else Path.home()) / "PurchaseOrderBot"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir / "config.json"


def _has_connection() -> bool:
    try:
        _ = get_config()
        return True
    except Exception:
        return False


def _setup_screen() -> None:
    # Setup page UI (page config already set at module import)
    st.title("Inventory Dashboard – First-time Setup")
    st.write(
        "To connect to SQL Server, paste your ODBC connection string. You can get this from IT or your DBA."
    )
    default = "Driver={ODBC Driver 18 for SQL Server};Server=YOUR_SERVER;Database=YOUR_DB;Trusted_Connection=Yes;Encrypt=no;"
    conn = st.text_input("SQLSERVER_ODBC", value="", placeholder=default)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Save and launch"):
            if not conn.strip():
                st.error("Connection string cannot be empty.")
            else:
                cfg_path = _user_config_path()
                try:
                    cfg_path.write_text(json.dumps({"SQLSERVER_ODBC": conn.strip()}, indent=2), encoding="utf-8")
                    st.success("Saved! Launching the dashboard…")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to save config: {e}")
    with col2:
        st.caption("The configuration is saved to your user profile so you only do this once.")


def main() -> None:
    if _has_connection():
        dashboard.run()
    else:
        _setup_screen()


if __name__ == "__main__":
    main()
