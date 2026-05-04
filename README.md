# Inventory Performance Dashboard

A Streamlit application that consolidates sales, purchasing, inventory, and receipt data from the NRF reporting SQL Server to help planners monitor stock health, fill rates, and lead times. The dashboard surfaces actionable alerts, highlights SKUs at risk of stocking out, and recommends reorder quantities based on real-time inventory positions and sales velocity.

## Features
- Centralized SQL Server data ingestion covering `_ORDERS`, `ROLLS`, `OPENIV`, `ITEM`, `PRICE`, and `PRODLINE` tables.
- Normalized unit conversions (linear feet/inches/yards to square yards) for consistent stock and sales comparison.
- Key performance indicators: stock turn vs target (4), backorder rate, days of inventory, aging inventory count, and runout risk.
- Automatic SKU rating tiers (A-E) based on sales velocity with interactive filters.
- Backorder tracker capturing lines flagged in `_ORDERS.DETAIL_LINE_STATUS`.
- Runout detection and reorder recommendations factoring on-hand, on-order, lead time, and a 1-week safety buffer.
- Drill-down tables for SKU metrics, open purchase orders, and raw sales orders plus CSV export support.

## Project structure
- `app/config.py` - loads global configuration and resolves the SQL Server connection string.
- `app/data/` - database utility, SQL queries, and typed loaders for each source table.
- `app/services/` - business logic for metric calculation, SKU ratings, alerts, and reorder planning.
- `app/ui/dashboard.py` - Streamlit presentation layer and user interaction hooks.
- `streamlit_app.py` - simple entry-point used by `streamlit run`.

## Prerequisites
- Python 3.10 or newer.
- Access to the NRF SQL Server with the ODBC Driver 18 (or compatible) installed.

## Setup
1. **Create a virtual environment (recommended)**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
2. **Install dependencies**
   ```powershell
   pip install -r requirements.txt
   ```
3. **Configure the SQL Server connection**
   Create a `config_local.py` file (ignored by git) in the project root with:
   ```python
   SQLSERVER_ODBC = (
       "Driver={ODBC Driver 18 for SQL Server};"
       "Server=NRFVMSSQL04;"
       "Database=NRF_REPORTS;"
       "Trusted_Connection=Yes;"
       "Encrypt=no;"
   )
   ```
   Adjust the server, database, or trust settings as required. You may also set an environment variable instead: `setx SQLSERVER_ODBC "Driver=...;"`.
4. **Run the dashboard**
   ```powershell
   streamlit run streamlit_app.py
   ```
   The app defaults to cost center 010. Use the sidebar to change cost centers, rating tiers, and date filters. By default, the order date range starts from 2025-08-04 (the beginning of data entry) through today.

## Packaging into an EXE (PyInstaller)

1. Create the virtual environment and install dependencies (see above). Then install PyInstaller:
    ```powershell
    .\.venv\Scripts\python.exe -m pip install pyinstaller
    ```
2. Build using the provided spec file:
    ```powershell
    .\.venv\Scripts\python.exe -m PyInstaller ".\Inventory Dashboard.spec" --clean --noconfirm
    ```
3. The EXE will be located at `dist/Inventory Dashboard/Inventory Dashboard.exe`.

Troubleshooting packaged EXE on other PCs
- Microsoft ODBC Driver 18 for SQL Server is required. If missing, the app shows a Windows message box and prints a link:
   https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server
- Configure a SQL connection: set the `SQLSERVER_ODBC` environment variable or create `%APPDATA%/PurchaseOrderBot/config.json` with:
   ```json
   {
      "SQLSERVER_ODBC": "Driver={ODBC Driver 18 for SQL Server};Server=NRFVMSSQL04;Database=NRF_REPORTS;Trusted_Connection=Yes;Encrypt=no;"
   }
   ```
- The app finds a free local port automatically; if a browser doesn’t open, check firewall rules or navigate to `http://127.0.0.1:8501` (or the port shown in the console output).
- App data is stored under `%APPDATA%/PurchaseOrderBot` (config, history). Delete files there to reset local state.

## Secure Portable Distribution (Recommended)

If internal security tools block generic PyInstaller executables, distribute a transparent, signed bundle:

Contents of the ZIP:
```
InventoryDashboard/
   app/                (source modules)
   streamlit_app.py
   launch_app.py       (programmatic Streamlit launcher)
   bootstrap.ps1       (signed PowerShell bootstrap script)
   requirements.txt    (pinned versions)
   vendor/             (optional wheel cache for offline install)
   README.md
```

### Steps for first-time user
1. Extract the ZIP to a local folder (not a network drive for best performance).
2. Double-click `Launch Dashboard.vbs` to start the app (no console window). If needed on first run, Windows may prompt about script execution—choose Run.
3. Advanced: you can also run `run-dashboard.bat` (console visible) or `bootstrap.ps1` directly from PowerShell.
4. The bootstrap creates `.venv`, installs dependencies (from `vendor/` if present), checks ODBC driver presence, then launches the app in the default browser.

### Signing & Integrity
- Sign `bootstrap.ps1` using your corporate code-signing certificate:
   ```powershell
   Set-AuthenticodeSignature -FilePath .\bootstrap.ps1 -Certificate (Get-ChildItem Cert:\CurrentUser\My\<Thumbprint>)
   ```
- Publish SHA256 hashes for all top-level files (store in an internal artifact system). Users can verify with:
   ```powershell
   Get-FileHash .\bootstrap.ps1 -Algorithm SHA256
   ```
- Optional: create a `requirements.lock.txt` with exact versions + hashes using:
   ```powershell
   pip freeze | Out-File requirements.lock.txt
   ```
   For deterministic installs add hashes: `pip-compile --generate-hashes` (requires pip-tools).

### Offline / Air‑gapped Mode
Place wheels in `vendor/` and run:
```powershell
./bootstrap.ps1 -Offline
```
No external network calls occur (assuming all wheels are present).

### Advantages vs Single EXE
- Transparent source reduces heuristic AV flags.
- Signed script + hashed requirements is easy to audit.
- Faster iteration: update only changed Python files without rebuilding an EXE.

### Optional: Minimal Signed EXE Wrapper
If users insist on double-click simplicity, keep PyInstaller but:
1. Pin versions. Avoid wildcard `>=`.
2. Use `--disable-windowed-traceback` and avoid bundling unused packages.
3. Sign the resulting EXE and publish its hash.
4. Still include `bootstrap.ps1` as fallback for machines that block the EXE.

## Operational Best Practices
- Roll out updates by replacing the ZIP; user’s `.venv` can be reused (bootstrap will upgrade packages as needed).
- Automate weekly dependency vulnerability scanning using `pip-audit` on CI before publishing.
- Maintain a changelog noting any metric logic adjustments for compliance review.

## Quick Start (Developer)
```powershell
python -m venv .venv
./.venv/Scripts/Activate.ps1
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Quick Start (User, Portable Bundle)
```powershell
./bootstrap.ps1   # launches the dashboard after environment prep
```

## Metric logic & assumptions
- **Unit normalization** - all quantities convert to square yards; linear inch/foot/yard measurements use the SKU width (`ITEM.IWIDTH` when available).
- **Sales window** - date filters apply to `_ORDERS` data; by default, the window starts at 2025-08-04 (first data entry) and ends at today.
- **Stock turn** - annualizes sales over the active window and divides by current on-hand stock.
- **Backorder rate** - the share of stocking order lines flagged as backorders (`DETAIL_LINE_STATUS` non-numeric or containing `B`).
- **Aging** - SKUs with no movement for 18+ months are counted as aging risk.
- **Lead time** - prefers `ITEM.IDELIV`, fallback to `PRODLINE.LDELIV`, then actual receipt history from `OPENIV` when available.
- **Reorder recommendation** - ensures cover for lead time plus a 7-day safety buffer: `(daily demand * (lead time + 7 days)) - (on-hand + on-order)`.

## Next steps
- Add authentication or row-level security if multiple departments share the tool.
- Extend charts (e.g., trend lines for stock turn or fill rate).
- Integrate write-backs for planners to acknowledge alerts or create purchase requests.
