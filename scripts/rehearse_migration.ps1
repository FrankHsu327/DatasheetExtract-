# Dress rehearsal of the company-machine install, run inside dist\datasheet-extractor (fresh copy, no venvs/tools):
#   setup_envs.ps1 (uv + Python from GitHub, torch from wheels\, rest from PyPI via lock files)
#   -> checksums verify -> offline_check with DSX_OFFLINE=1
$root = Split-Path $PSScriptRoot -Parent
$dist = "$root\dist\datasheet-extractor"
Set-Location $dist
"== setup in $dist  $(Get-Date -Format s)"
powershell -ExecutionPolicy Bypass -File scripts\setup_envs.ps1
"== checksums  $(Get-Date -Format s)"
& .\.venv-docling\Scripts\python.exe scripts\checksums.py . verify
"== offline check  $(Get-Date -Format s)"
$env:DSX_OFFLINE = "1"
$env:PYTHONIOENCODING = "utf-8"
& .\.venv-docling\Scripts\python.exe scripts\offline_check.py datasheet\0900766b81703faf.pdf 61-63
"== REHEARSAL DONE  $(Get-Date -Format s)"
# 演練產生的 venv / tools / logs / out 不屬於要搬的內容（venv 含絕對路徑），清掉讓 dist 保持可直接複製
Set-Location $root
foreach ($d in ".venv-docling", "tools", "logs", "out") {
  if (Test-Path "$dist\$d") { Remove-Item -Recurse -Force "$dist\$d" }
}
"== dist cleaned"
