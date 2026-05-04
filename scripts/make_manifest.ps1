# Generates manifest.json with SHA256 hashes for portable distribution integrity
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\scripts\make_manifest.ps1
# Output:
#   manifest.json in repo root

param(
    [string]$Output = "manifest.json",
    [switch]$IncludeVendor
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $Root   # move from scripts/ to repo root
Set-Location $Root

function Should-Include($path) {
    $p = $path.ToLowerInvariant()
    $excludes = @(".git", ".venv", "__pycache__", "build", "dist", ".streamlit")
    foreach ($e in $excludes) { if ($p -like "*$e*") { return $false } }
    return $true
}

$files = @()

# Top-level files
$top = Get-ChildItem -File | Where-Object { Should-Include $_.FullName } |
    Where-Object { $_.Name -match '\.(ps1|py|md|txt|bat|json)$' }
$files += $top

# Remove manifest.json itself if present to avoid self-hash instability
$files = $files | Where-Object { $_.Name -ne 'manifest.json' }

# app tree (source only)
$appFiles = Get-ChildItem -Recurse -File -Path "$Root/app" |
    Where-Object { Should-Include $_.FullName } |
    Where-Object { $_.Name -match '\.(py|sql|json)$' }
$files += $appFiles

# Optional vendor wheels
if ($IncludeVendor -and (Test-Path (Join-Path $Root 'vendor'))) {
    $vendorFiles = Get-ChildItem -Recurse -File -Path "$Root/vendor" |
        Where-Object { Should-Include $_.FullName } |
        Where-Object { $_.Name -match '\.(whl|txt|json)$' }
    $files += $vendorFiles
}

$entries = @()
foreach ($f in $files) {
    $hash = Get-FileHash -Path $f.FullName -Algorithm SHA256
    $rel = Resolve-Path -Relative $f.FullName
    $entries += [pscustomobject]@{
        path   = $rel
        sha256 = $hash.Hash
        size   = $f.Length
    }
}

$manifest = [pscustomobject]@{
    generatedAt   = (Get-Date).ToString("s")
    hashAlgorithm = 'SHA256'
    files         = $entries | Sort-Object path
}

$manifest | ConvertTo-Json -Depth 5 | Out-File -FilePath (Join-Path $Root $Output) -Encoding utf8

Write-Host "Manifest written to $Output with $($entries.Count) files." -ForegroundColor Cyan
