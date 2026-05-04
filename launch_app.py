import os
import sys
import socket

try:
    import ctypes
    _HAS_CTYPE = True
except Exception:
    _HAS_CTYPE = False

try:
    # Streamlit CLI entry so we can bundle as an EXE
    import streamlit.web.cli as stcli
except Exception:
    print("Streamlit is not installed in this environment. Install dependencies with 'pip install -r requirements.txt'.")
    raise


def resource_path(rel: str) -> str:
    """Return absolute path to resource, working in PyInstaller one-file mode too."""
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, rel)


def _preflight_checks() -> None:
    # Check for required ODBC driver presence to avoid confusing runtime errors
    try:
        import pyodbc  # type: ignore
        try:
            drivers = [d.lower() for d in pyodbc.drivers()]
        except Exception:
            drivers = []
        has_ms18 = any("odbc driver 18 for sql server" in d for d in drivers)
        if not has_ms18:
            msg = (
                "Microsoft ODBC Driver 18 for SQL Server is required but not installed.\n\n"
                "Please install it from your IT software catalog or:\n"
                "https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server\n\n"
                "After installing, re-launch Inventory Dashboard."
            )
            if _HAS_CTYPE:
                try:
                    ctypes.windll.user32.MessageBoxW(0, msg, "Missing prerequisite", 0x10)
                except Exception:
                    pass
            print("WARNING:", msg)
    except Exception:
        # pyodbc import failed; requirements may not be installed in this env (fine for packaged EXE)
        pass

    # Check for connection string env var
    if not os.environ.get("SQLSERVER_ODBC"):
        note = (
            "SQLSERVER_ODBC environment variable is not set.\n\n"
            "Set it in Windows Environment Variables or create %APPDATA%/PurchaseOrderBot/config.json with:\n"
            '{"SQLSERVER_ODBC": "Driver={ODBC Driver 18 for SQL Server};Server=...;Database=...;Trusted_Connection=Yes;Encrypt=no;"}'
        )
        if _HAS_CTYPE:
            try:
                ctypes.windll.user32.MessageBoxW(0, note, "Connection not configured", 0x30)
            except Exception:
                pass
        print("NOTE:", note)


def _find_free_port(start: int = 8501, tries: int = 20) -> int:
    """Find a free TCP port starting from 'start'. Returns the first free port or the start value if none found."""
    port = start
    for _ in range(max(1, tries)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                port += 1
    return start


def main() -> int:
    """Console entry point: run the Streamlit app programmatically."""
    _preflight_checks()
    app_path = resource_path("streamlit_app.py")
    # Force stable runtime settings via env to avoid user config conflicts
    # Disable development mode to avoid assertion conflict with server.port
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"
    # Back-compat alias in case older mapping is used
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENTMODE"] = "false"
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "false"
    os.environ["STREAMLIT_SERVER_ADDRESS"] = "127.0.0.1"
    # Pick an available port to avoid conflicts; fall back to 8501
    port = _find_free_port(8501, tries=20)
    os.environ["STREAMLIT_SERVER_PORT"] = str(port)
    # Let Streamlit open the browser by default for a click-and-run experience
    sys.argv = [
        "streamlit",
        "run",
        app_path,
    ]
    return stcli.main()


if __name__ == "__main__":
    sys.exit(main())
