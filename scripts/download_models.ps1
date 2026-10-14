# Download all model weights into models\ (run on a machine that can reach huggingface.co).
$env:TEMP = "$env:USERPROFILE\AppData\Local\Temp"; $env:TMP = $env:TEMP
$env:PYTHONIOENCODING = "utf-8"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$log = "$root\logs\download_models.log"
"start $(Get-Date -Format s)" | Out-File $log -Encoding utf8
& .\.venv-docling\Scripts\python.exe scripts\download_models.py 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $log -Append
"ALL DONE $(Get-Date -Format s)" | Tee-Object -FilePath $log -Append
