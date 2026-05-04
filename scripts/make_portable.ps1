param(
  [switch]$IncludeVendor,
  [switch]$DownloadVendor,
  [string]$OutputName = 'InventoryDashboard-portable.zip'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$Repo = Split-Path -Parent $Repo
Set-Location $Repo

function Write-Info($msg){ Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Clean-Dir($path){ if(Test-Path $path){ Remove-Item -Recurse -Force $path } ; New-Item -ItemType Directory -Path $path | Out-Null }

# Optionally download vendor wheels
if ($DownloadVendor) {
  $vendor = Join-Path $Repo 'vendor'
  if (!(Test-Path $vendor)) { New-Item -ItemType Directory -Path $vendor | Out-Null }
  $py = Join-Path $Repo '.venv/\Scripts/python.exe'
  if (!(Test-Path $py)) { throw ".venv Python not found at $py" }
  $lock = Join-Path $Repo 'requirements.lock.txt'
  $req  = Join-Path $Repo 'requirements.txt'
  $reqFile = $req
  if (Test-Path $lock) { $reqFile = $lock }
  Write-Info "Downloading wheels to vendor from $([IO.Path]::GetFileName($reqFile))"
  & $py -m pip download -d $vendor -r $reqFile
}

# Build staging folder excluding caches
$StagingRoot = Join-Path $Repo 'dist_portable'
$BundleName = 'InventoryDashboard'
$Stage = Join-Path $StagingRoot $BundleName
if (!(Test-Path $StagingRoot)) { New-Item -ItemType Directory -Path $StagingRoot | Out-Null }
Clean-Dir $Stage

# Include list
$include = @('app','streamlit_app.py','launch_app.py','bootstrap.ps1','README.md','requirements.txt','requirements.lock.txt','manifest.json','run-dashboard.bat','config_local.sample.py','Launch Dashboard.vbs')
foreach ($item in $include) {
  $src = Join-Path $Repo $item
  if (Test-Path $src) {
    if (Test-Path $src -PathType Container) {
      Copy-Item $src -Destination $Stage -Recurse -Force -Exclude '__pycache__','*.pyc','*.pyo'
    } else {
      Copy-Item $src -Destination $Stage -Force
    }
  }
}

if ($IncludeVendor -and (Test-Path (Join-Path $Repo 'vendor'))) {
  Copy-Item (Join-Path $Repo 'vendor') -Destination $Stage -Recurse -Force
}

# Remove any __pycache__ that slipped through
Get-ChildItem -Recurse -Directory -Path $Stage -Filter '__pycache__' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# Create ZIP
if (!(Test-Path $StagingRoot)) { New-Item -ItemType Directory -Path $StagingRoot | Out-Null }
$ZipPath = Join-Path $StagingRoot $OutputName
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Write-Info "Creating ZIP at $ZipPath"
Compress-Archive -Path (Join-Path $Stage '*') -DestinationPath $ZipPath -Force
Write-Host "ZIP created: $ZipPath" -ForegroundColor Green
