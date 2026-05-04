# Bootstrap launcher for Inventory Dashboard (Portable, Secure Bundle)
# - Creates/uses a local virtual environment under .venv
# - Installs dependencies (offline from ./vendor if present; otherwise from PyPI)
# - Verifies essential prerequisites (ODBC Driver 18; SQLSERVER_ODBC variable or config file)
# - Launches the Streamlit app via launch_app.py (opens a local browser)
#
# Optional hardening:
# - Sign this script with your corporate code-signing cert
# - Distribute a requirements.lock.txt with pinned versions and run with --require-hashes
# - Place wheels in ./vendor for offline and deterministic installs

param(
    [switch]$Offline,              # Force offline install from ./vendor only
    [switch]$NoInstall,            # Skip dependency installation
    [switch]$Quiet,                # Reduce output noise
    [switch]$SkipIntegrity,        # Skip integrity manifest verification
    [switch]$StrictIntegrity       # Fail fast if integrity check fails
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Info($msg) { if (-not $Quiet) { Write-Host "[INFO] $msg" -ForegroundColor Cyan } }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "[ERR ] $msg" -ForegroundColor Red }

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

# Integrity verification (optional via manifest.json)
function Verify-Integrity {
    param(
        [string]$ManifestPath
    )
    if (-not (Test-Path $ManifestPath)) { return $true }

    try {
        $json = Get-Content $ManifestPath -Raw | ConvertFrom-Json
        if (-not $json.files) { return $true }
        $algo = if ($json.hashAlgorithm) { $json.hashAlgorithm } else { 'SHA256' }
        $failed = @()
        foreach ($f in $json.files) {
            $p = Join-Path $Root $f.path
            if (-not (Test-Path $p)) {
                $failed += "missing: $($f.path)"
                continue
            }
            $h = Get-FileHash -Path $p -Algorithm $algo
            if ($h.Hash -ne $f.sha256) {
                $failed += "mismatch: $($f.path) expected=$($f.sha256) actual=$($h.Hash)"
            }
        }
        if ($failed.Count -gt 0) {
            Write-Err "Integrity check FAILED for $($failed.Count) file(s):"
            $failed | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
            return $false
        }
        else {
            Write-Info "Integrity check passed (manifest.json)"
            return $true
        }
    }
    catch {
        Write-Warn "Integrity check skipped (invalid manifest.json): $($_.Exception.Message)"
        return $true
    }
}

# Run integrity verification unless skipped
if (-not $SkipIntegrity) {
    $ok = Verify-Integrity -ManifestPath (Join-Path $Root 'manifest.json')
    if (-not $ok -and $StrictIntegrity) {
        Write-Err "Aborting due to failed integrity verification (StrictIntegrity)."
        exit 2
    }
}

# Detect Python
function Find-Python {
    $candidates = @(
        (Join-Path $Root ".venv\Scripts\python.exe")
        "py -3.11"
        "py -3.10"
        "python"
    )
    foreach ($c in $candidates) {
        try {
            if ($c -like "*.exe" -and (Test-Path $c)) { return $c }
            # test command existence by requesting version
            $null = & $c --version 2>$null
            if ($LASTEXITCODE -eq 0) { return $c }
        } catch { }
    }
    return $null
}

$py = Find-Python
if (-not $py) {
    Write-Err "Python 3.10+ not found. Install Python or provide an embedded runtime."
    Write-Host "Download: https://www.python.org/downloads/windows/"
    exit 1
}

# Create venv if missing
$venvPy = Join-Path $Root ".venv/Scripts/python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Info "Creating virtual environment (.venv)"
    & $py -m venv .venv
}

$py = $venvPy

# Install dependencies unless suppressed
if (-not $NoInstall) {
    Write-Info "Upgrading pip"
    & $py -m pip install --upgrade pip

    $reqFile = Join-Path $Root "requirements.txt"
    $lockFile = Join-Path $Root "requirements.lock.txt"
    $vendor = Join-Path $Root "vendor"

    if (Test-Path $lockFile) {
        Write-Info "Installing from requirements.lock.txt (prefer exact pins)"
        $lockContent = try { Get-Content $lockFile -Raw } catch { '' }
        $hasHashes = $false
        if ($lockContent -match '--hash=' -or $lockContent -match 'sha256:') { $hasHashes = $true }
        if (Test-Path $vendor) {
            if ($Offline) {
                & $py -m pip install --no-index --find-links $vendor -r $lockFile
            } else {
                & $py -m pip install --find-links $vendor -r $lockFile
            }
        } else {
            if ($hasHashes) {
                & $py -m pip install -r $lockFile --require-hashes
            } else {
                & $py -m pip install -r $lockFile
            }
        }
    } else {
        Write-Info "Installing from requirements.txt"
        if ((Test-Path $vendor) -and $Offline) {
            & $py -m pip install --no-index --find-links $vendor -r $reqFile
        } elseif (Test-Path $vendor) {
            # Prefer wheels in vendor; fall back to PyPI for missing deps
            & $py -m pip install --find-links $vendor -r $reqFile
        } else {
            & $py -m pip install -r $reqFile
        }
    }
}

# Prerequisite checks (mirrors launch_app.py)
try {
    $pyCmd = @'
import sys
try:
    import pyodbc
    print(";".join(d.lower() for d in pyodbc.drivers()))
except Exception:
    print("")
'@
    $drivers = & $py -c $pyCmd 2>$null
    if ($LASTEXITCODE -ne 0) { $drivers = "" }
    if ($drivers -notmatch "odbc driver 18 for sql server") {
        Write-Warn "Microsoft ODBC Driver 18 for SQL Server not detected. Install it if connection fails."
        Write-Host "https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server"
    }
} catch { Write-Warn "Unable to query ODBC drivers (pyodbc not installed yet?)." }

if (-not $env:SQLSERVER_ODBC) {
    Write-Warn "SQLSERVER_ODBC environment variable is not set. The app may read %APPDATA%/PurchaseOrderBot/config.json instead."
}

# Launch the app via launch_app.py (picks an available port and opens a browser)
Write-Info "Starting dashboard..."
& $py "$Root/launch_app.py"

exit $LASTEXITCODE
