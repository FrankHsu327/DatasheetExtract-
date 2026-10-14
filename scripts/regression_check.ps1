# Full regression after a refactor: hybrid on all PDFs → out\review, real-datasheet test, compare with archive.
$env:PYTHONIOENCODING = "utf-8"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
powershell -ExecutionPolicy Bypass -File scripts\run_all.ps1
"===== slow test  $(Get-Date -Format s)"
$env:DSX_SLOW = "1"
& .\.venv-docling\Scripts\python.exe -m pytest -q -p no:cacheprovider tests\test_real_datasheet.py
"===== regression vs archive  $(Get-Date -Format s)"
& .\.venv-docling\Scripts\python.exe scripts\regression_vs_archive.py
"REGRESSION CHECK DONE $(Get-Date -Format s)"
