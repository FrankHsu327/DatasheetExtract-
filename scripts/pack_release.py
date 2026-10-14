"""Pack models/ (and optionally wheels/) into split zip parts for GitHub Release assets (each asset < 2 GB).

  .venv-docling\\Scripts\\python.exe scripts\\pack_release.py [--wheels]

Output dist/github_release/:
  models-docling.zip.001, .002, ...    ZIP64, stored (safetensors/onnx do not compress), split at 1900 MiB
  wheels-torch-cu126.zip.001, ...      (--wheels) torch / torchvision CUDA 12.6 wheels
  SHA256SUMS.txt                       sha256 of every part and of each joined zip
On the target machine: scripts/fetch_models.ps1 downloads, verifies, joins and extracts them.
"""
import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dist" / "github_release"
PART = 1900 * 1024 * 1024


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def pack(name: str, src: Path, arc_root: str) -> list[tuple[str, str]]:
    zpath = OUT / f"{name}.zip"
    files = sorted(p for p in src.rglob("*") if p.is_file() and ".cache" not in p.parts)
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        for p in files:
            zf.write(p, f"{arc_root}/{p.relative_to(src).as_posix()}")
    sums = [(sha256(zpath), zpath.name)]
    with open(zpath, "rb") as f:
        i = 1
        while chunk := f.read(PART):
            part = OUT / f"{zpath.name}.{i:03d}"
            part.write_bytes(chunk)
            sums.append((sha256(part), part.name))
            print(f"  {part.name}  {len(chunk) / 2**20:,.0f} MiB", flush=True)
            i += 1
    zpath.unlink()   # 只上傳分割檔；完整 zip 的 sha256 保留在清單中，合併後可驗證
    print(f"{name}: {len(files)} files -> {i - 1} parts")
    return sums


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*"):
        old.unlink()
    sums = pack("models-docling", ROOT / "models" / "docling", "models/docling")
    if "--wheels" in sys.argv:
        sums += pack("wheels-torch-cu126", ROOT / "wheels", "wheels")
    (OUT / "SHA256SUMS.txt").write_text("".join(f"{h}  {n}\n" for h, n in sums), encoding="utf-8")
    print("PACK DONE", OUT)


if __name__ == "__main__":
    main()
