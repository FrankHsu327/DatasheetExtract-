"""Per-figure match status for one datasheet, all methods (from evaluate.json) + pictures on those pages."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datasheet_extractor.docling_reader import DoclingDoc  # noqa: E402

d = Path(sys.argv[1])
methods = sys.argv[2].split(",") if len(sys.argv) > 2 else None
for m in sorted(p for p in d.iterdir() if (p / "evaluate.json").exists()):
    if methods and m.name not in methods:
        continue
    fig = json.loads((m / "evaluate.json").read_text(encoding="utf-8")).get("figures") or {}
    print(f"== {m.name}: found {fig.get('found')}/{fig.get('golden_count')}, pictures total {fig.get('pictures_total')}")
    doc = DoclingDoc.load(m / "01_docling" / "document.json")
    by_page = {}
    for p in doc.data.get("pictures", []):
        pv = doc.provenance(p)
        by_page.setdefault(pv[0]["page"] if pv else None, []).append(doc.caption_text(p)[:50])
    for det in fig.get("details", []):
        if not det["found"]:
            print(f"   MISSED p{det['page']} {det['label']}; pictures on page: {by_page.get(det['page'], [])}")
