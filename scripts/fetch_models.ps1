# Download the model weights (and optionally the torch CUDA wheels) from this repository's GitHub Release,
# verify SHA-256, join the split parts and extract into models\ (and wheels\). Needs only GitHub access.
#
#   powershell -ExecutionPolicy Bypass -File scripts\fetch_models.ps1                     # models only
#   powershell -ExecutionPolicy Bypass -File scripts\fetch_models.ps1 -Wheels             # + torch wheels
#   powershell -ExecutionPolicy Bypass -File scripts\fetch_models.ps1 -From D:\downloads  # parts already downloaded by hand
param(
  [string]$Repo = "FrankHsu327/DatasheetExtract-",
  [string]$Tag = "models-v1",
  [string]$From = "",
  [switch]$Wheels
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest 的進度列會讓大檔下載慢很多
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$dl = if ($From) { $From } else { "$root\dist\github_release" }
New-Item -ItemType Directory -Force $dl | Out-Null
$base = "https://github.com/$Repo/releases/download/$Tag"

function Get-Asset($name) {
  $dst = Join-Path $dl $name
  if (-not (Test-Path $dst)) {
    if ($From) { throw "missing $dst" }
    Write-Host "download $name"   # Write-Host：不能進 pipeline，否則會混進回傳值
    Invoke-WebRequest "$base/$name" -OutFile $dst -UseBasicParsing
  }
  return $dst
}

$sumsFile = Get-Asset "SHA256SUMS.txt"
$sums = @{}
Get-Content $sumsFile | ForEach-Object { $h, $n = $_ -split "  ", 2; $sums[$n.Trim()] = $h.Trim() }

$sets = @("models-docling")
if ($Wheels) { $sets += "wheels-torch-cu126" }
foreach ($set in $sets) {
  $parts = $sums.Keys | Where-Object { $_ -like "$set.zip.*" } | Sort-Object
  if (-not $parts) { throw "no parts for $set in SHA256SUMS.txt" }
  foreach ($p in $parts) {
    $f = Get-Asset $p
    if ((Get-FileHash $f -Algorithm SHA256).Hash.ToLower() -ne $sums[$p]) { throw "checksum mismatch: $p (delete it and run again)" }
    "ok  $p"
  }
  $zip = Join-Path $dl "$set.zip"
  "join -> $zip"
  $out = [System.IO.File]::Create($zip)
  try {
    foreach ($p in $parts) { $in = [System.IO.File]::OpenRead((Join-Path $dl $p)); $in.CopyTo($out); $in.Close() }
  } finally { $out.Close() }
  if ((Get-FileHash $zip -Algorithm SHA256).Hash.ToLower() -ne $sums["$set.zip"]) { throw "checksum mismatch after join: $set.zip" }
  "extract $set.zip"
  tar -xf $zip -C $root
  if ($LASTEXITCODE -ne 0) { throw "extract failed: $set.zip" }
  Remove-Item $zip
}
"FETCH DONE  (models\docling" + $(if ($Wheels) { ", wheels" } else { "" }) + ")"
