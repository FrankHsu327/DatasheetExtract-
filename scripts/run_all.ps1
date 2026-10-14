# Run the hybrid on every PDF in datasheet\ → out\review\<stem>\compare.html + out\review\index.html.
#   powershell -File scripts\run_all.ps1 [-Reuse]     (-Reuse: keep Stage 1 output, rerun Stage 2-4 + scoring only)
# Golden: golden\<key>.golden.json (PDF file names differ from part names, mapped below).
param([switch]$Reuse)
$env:PYTHONIOENCODING = "utf-8"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$golden = @{
  "0900766b81703faf" = "W25Q128JV"
  "DS3624LE-00" = "DS3624LE-00"
  "MC9S08SC4" = "MC9S08SC4"
  "infineon-ez-pd-ccg6-cfp-usb-c-power-delivery-controller-datasheet-en" = "CCG6"
}
foreach ($pdf in Get-ChildItem datasheet\*.pdf) {
  $a = @("-m", "datasheet_extractor", "view", $pdf.FullName, "--out", "out\review", "--component", "generic")
  if ($Reuse) { $a += "--reuse" }
  $g = "golden\$($golden[$pdf.BaseName]).golden.json"
  if ($golden.ContainsKey($pdf.BaseName) -and (Test-Path $g)) { $a += @("--golden", $g) }
  "===== $($pdf.Name)  $(Get-Date -Format s)"
  & .\.venv-docling\Scripts\python.exe @a
}
& .\.venv-docling\Scripts\python.exe -m datasheet_extractor summary --out out\review
"ALL DONE $(Get-Date -Format s)"
