# Build the venv. Works on this machine and on the company machine (GitHub + PyPI, no HuggingFace).
#
#   powershell -ExecutionPolicy Bypass -File scripts\setup_envs.ps1
#
# 1. uv          : tools\uv\uv.exe, downloaded from GitHub releases if missing
# 2. Python 3.11 : standalone CPython via `uv python install` (GitHub) into tools\python
#                  (Anaconda's Python is NOT used: its msvcp140.dll 14.27 breaks torch >= 2.x on Windows)
# 3. torch       : CUDA 12.6 wheels from wheels\ if present (bundled), else download.pytorch.org
# 4. the rest    : PyPI, pinned by requirements\lock-docling.txt when present
#
#   .venv-docling : pdfplumber + docling (layout, TableFormer, picture classifier) + transformers (Granite Vision)
# Log: logs\setup_envs.log (UTF-8). Needs NVIDIA driver >= 561 for CUDA 12.6.
param([string]$UvVersion = "0.13.0", [string]$TorchIndex = "https://download.pytorch.org/whl/cu126")
$ErrorActionPreference = "Continue"
$env:TEMP = "$env:USERPROFILE\AppData\Local\Temp"; $env:TMP = $env:TEMP
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
New-Item -ItemType Directory -Force logs, tools | Out-Null
$log = "$root\logs\setup_envs.log"
"setup start $(Get-Date -Format s)" | Out-File $log -Encoding utf8

function Step($msg) { "`n===== $msg  $(Get-Date -Format s) =====" | Tee-Object -FilePath $log -Append | Write-Host }
function Run { param([string]$exe, [string[]]$a) & $exe @a 2>&1 | ForEach-Object { "$_" } | Out-File $log -Append -Encoding utf8 }

$uv = "$root\tools\uv\uv.exe"
if (-not (Test-Path $uv) -and (Test-Path "$root\tools\uv\bin\uv.exe")) { $uv = "$root\tools\uv\bin\uv.exe" }
if (-not (Test-Path $uv)) {
  Step "download uv $UvVersion from GitHub"
  $zip = "$env:TEMP\uv-$UvVersion.zip"
  Invoke-WebRequest "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-x86_64-pc-windows-msvc.zip" -OutFile $zip -UseBasicParsing
  Expand-Archive $zip -DestinationPath "$root\tools\uv" -Force
  $uv = "$root\tools\uv\uv.exe"
}
$env:UV_PYTHON_INSTALL_DIR = "$root\tools\python"
Step "install standalone CPython 3.11"
Run $uv @("python", "install", "3.11")
$py = (& $uv python find 3.11 --managed-python 2>$null | Select-Object -First 1)
"python: $py" | Tee-Object -FilePath $log -Append | Write-Host

$venv = "$root\.venv-docling"
$vpy = "$venv\Scripts\python.exe"
$lock = "$root\requirements\lock-docling.txt"
$wheels = "$root\wheels"
Step "create $venv"
if (Test-Path $venv) { Remove-Item -Recurse -Force $venv }
Run $uv @("venv", "--seed", "--python", $py, $venv)
Run $vpy @("-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools")

$torchSpec = @("torch", "torchvision")
if (Test-Path $lock) { $torchSpec = @(Get-Content $lock | Where-Object { $_ -match '^(torch|torchvision)==' }) }
Step "torch ($($torchSpec -join ' '))"
# wheels\ 只有 torch / torchvision 本體；它們的相依（filelock、sympy…）在 lock 檔內，下一步從 PyPI 安裝
if (Test-Path $wheels) { Run $vpy (@("-m", "pip", "install", "--no-index", "--no-deps", "--find-links", $wheels) + $torchSpec) }
else { Run $vpy (@("-m", "pip", "install", "--index-url", $TorchIndex) + $torchSpec) }

Step "packages"
if (Test-Path $lock) {
  # torch 已裝好；其餘依 lock 檔從 PyPI 安裝（--no-deps 確保版本與這裡測過的一致）
  $rest = "$root\logs\lock-docling-rest.txt"
  Get-Content $lock | Where-Object { $_ -notmatch '^(torch|torchvision)==' } | Set-Content $rest -Encoding ascii
  Run $vpy @("-m", "pip", "install", "--no-deps", "-r", $rest)
} else {
  Run $vpy @("-m", "pip", "install", "docling[vlm]", "-r", "requirements.txt", "huggingface_hub")
}

Step "verify"
Run $vpy @("-c", "import torch, docling, pdfplumber, transformers; from importlib.metadata import version as v; print('VERIFY docling', v('docling'), 'transformers', v('transformers'), 'torch', torch.__version__, 'cuda', torch.cuda.is_available())")
Get-Content $log | Select-String "VERIFY" | ForEach-Object { $_.Line }
Step "SETUP DONE"
