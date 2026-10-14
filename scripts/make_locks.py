"""Write requirements/lock-docling.txt from the current venv (exact versions that were tested here).

  .venv-docling\\Scripts\\python.exe scripts\\make_locks.py

torch / torchvision 行保留 +cu126 版號，安裝時從 wheels\\（或 download.pytorch.org）取得。
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
out_dir = ROOT / "requirements"
out_dir.mkdir(exist_ok=True)
py = ROOT / ".venv-docling" / "Scripts" / "python.exe"
lines = subprocess.run([str(py), "-m", "pip", "freeze", "--exclude-editable"], capture_output=True,
                       text=True, check=True).stdout.splitlines()
lines = [ln for ln in lines if ln and not ln.startswith(("-e ", "pip==", "setuptools==", "wheel=="))]
(out_dir / "lock-docling.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("docling", len(lines), "packages")
