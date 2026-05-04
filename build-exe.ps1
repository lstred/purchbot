param(
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'

# Resolve project root (folder containing this script)
$PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $PSScriptRoot

# Paths
$venvPython = Join-Path $PSScriptRoot ".venv/Scripts/python.exe"
$specPath   = Join-Path $PSScriptRoot "Inventory Dashboard.spec"
$distDir    = Join-Path $PSScriptRoot "dist"
$buildDir   = Join-Path $PSScriptRoot "build"

Write-Host "Using Python: $venvPython"
Write-Host "Spec file:   $specPath"

if ($Clean) {
    Write-Host "Cleaning previous build artifacts..."
    if (Test-Path $distDir) { Remove-Item -Recurse -Force $distDir }
    if (Test-Path $buildDir) { Remove-Item -Recurse -Force $buildDir }
}

# Ensure tooling
& $venvPython -m pip install --upgrade pip setuptools wheel pyinstaller

# Build
& $venvPython -m PyInstaller -y $specPath

# Report result
$exePath = Join-Path $PSScriptRoot "dist/Inventory Dashboard/Inventory Dashboard.exe"
if (Test-Path $exePath) {
    $info = Get-Item $exePath
    Write-Host "\nBuild complete: $($info.FullName)" -ForegroundColor Green
    Write-Host "Size: $([Math]::Round($info.Length / 1MB, 2)) MB" -ForegroundColor Green
} else {
    Write-Host "\nBuild finished, but EXE not found where expected. Check the 'dist' folder." -ForegroundColor Yellow
}