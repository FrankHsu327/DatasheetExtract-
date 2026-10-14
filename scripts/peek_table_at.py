"""Debug one table: find tables on a page containing a text, print hybrid source + Docling original grid + final grid.

  python scripts/peek_table_at.py <stem_dir> <text in table> [page]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datasheet_extractor.docling_reader import DoclingDoc, table_grid  # noqa: E402

stem, needle = Path(sys.argv[1]), sys.argv[2]
for method in ("docling", "hybrid"):
    doc = DoclingDoc.load(stem / method / "01_docling" / "document.json")
    meta = json.loads((stem / method / "01_docling" / "meta.json").read_text(encoding="utf-8"))
    hyb = {t.get("table"): t for t in (meta.get("hybrid") or {}).get("tables", [])}
    for i, t in enumerate(doc.data["tables"]):
        grid, _ = table_grid(t)
        flat = " ".join(c for row in grid for c in row)
        if needle not in flat:
            continue
        pv = doc.provenance(t)[0]
        print(f"===== {method} table {i} page {pv['page']} bbox {[round(v) for v in pv['bbox']]} "
              f"{len(grid)}x{len(grid[0]) if grid else 0}  hybrid: {hyb.get(i)}")
        cells = t["data"]["table_cells"]
        big = [c for c in cells if (c["end_row_offset_idx"] - c["start_row_offset_idx"]) > 1
               or (c["end_col_offset_idx"] - c["start_col_offset_idx"]) > 1]
        for c in big:
            print(f"   span cell r{c['start_row_offset_idx']}-{c['end_row_offset_idx']} "
                  f"c{c['start_col_offset_idx']}-{c['end_col_offset_idx']}: {c['text'][:80]!r}")
        for row in grid[:9]:
            print("   ", [x[:18] for x in row])
