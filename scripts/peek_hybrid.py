"""Show hybrid meta (table sources / disagreement / figures) and the first rows of each table + picture descriptions."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datasheet_extractor.docling_reader import DoclingDoc, table_grid  # noqa: E402
from datasheet_extractor.figures import picture_description  # noqa: E402

d = Path(sys.argv[1])
meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))["hybrid"]
print("sources:", meta["table_sources"], "figures:", meta["figures"])
for t in meta["tables"]:
    print("  ", t)
doc = DoclingDoc.load(d / "document.json")
for i, t in enumerate(doc.data["tables"]):
    grid, _ = table_grid(t)
    print(f"--- table {i} p{t['prov'][0]['page_no']} {len(grid)}x{len(grid[0]) if grid else 0}")
    for row in grid[:int(sys.argv[2]) if len(sys.argv) > 2 else 5]:
        print("    ", row)
for p in doc.data.get("pictures", []):
    desc = picture_description(p)
    if desc:
        print(f"=== picture p{p['prov'][0]['page_no']} {doc.caption_text(p)[:70]!r}\n{desc}\n")
