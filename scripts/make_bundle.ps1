# Build the migration bundle: dist\datasheet-extractor\ = code + models\ + wheels\ (torch CUDA) + locks.
# Copy that folder to the company machine, then run scripts\setup_envs.ps1 there and scripts\offline_check.py.
#
#   powershell -ExecutionPolicy Bypass -File scripts\make_bundle.ps1
$ErrorActionPreference = "Continue"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$py = ".\.venv-docling\Scripts\python.exe"

"== locks"
& $py scripts\make_locks.py

"== torch CUDA wheels (download.pytorch.org may be unreachable from the company network)"
New-Item -ItemType Directory -Force wheels | Out-Null
$torch = Get-Content requirements\lock-docling.txt | Where-Object { $_ -match '^(torch|torchvision)==' }
& $py -m pip download --no-deps --dest wheels --index-url https://download.pytorch.org/whl/cu126 @torch
Get-ChildItem wheels | ForEach-Object { "{0,-60} {1,8:N0} MB" -f $_.Name, ($_.Length / 1MB) }

"== copy to dist\datasheet-extractor"
$dst = "$root\dist\datasheet-extractor"
New-Item -ItemType Directory -Force $dst | Out-Null
robocopy $root $dst /E /NFL /NDL /NJH /NP /XD .venv-docling .venv tools out logs dist __pycache__ .pytest_cache .claude debug /XF *.pyc probe_*.log find_py.log | Out-Null
$size = (Get-ChildItem $dst -Recurse -File | Measure-Object Length -Sum).Sum
"bundle: $dst  {0:N2} GB" -f ($size / 1GB)
"== checksums"
& $py scripts\checksums.py $dst write
"BUNDLE DONE"
