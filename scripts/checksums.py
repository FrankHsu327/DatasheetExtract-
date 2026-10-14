"""SHA-256 of every file under models\\ and wheels\\ — write on the source machine, verify after copying.

  python scripts\\checksums.py <bundle_dir> write     → <bundle_dir>\\CHECKSUMS.sha256
  python scripts\\checksums.py <bundle_dir> verify    → lists missing / mismatched files
"""
import hashlib
import sys
from pathlib import Path

root, mode = Path(sys.argv[1]), sys.argv[2]
listing = root / "CHECKSUMS.sha256"


def digest(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


files = sorted(p for d in ("models", "wheels") if (root / d).exists() for p in (root / d).rglob("*")
               if p.is_file() and ".cache" not in p.parts)
if mode == "write":
    listing.write_text("".join(f"{digest(p)}  {p.relative_to(root).as_posix()}\n" for p in files), encoding="utf-8")
    print(f"{len(files)} files -> {listing}")
else:
    bad = 0
    for line in listing.read_text(encoding="utf-8").splitlines():
        h, rel = line.split("  ", 1)
        p = root / rel
        if not p.exists():
            print("MISSING ", rel); bad += 1
        elif digest(p) != h:
            print("MISMATCH", rel); bad += 1
    print("CHECKSUMS OK" if not bad else f"CHECKSUMS FAILED: {bad}")
    sys.exit(1 if bad else 0)
