"""Find tables whose cells overlap (a 'frame' cell containing other cells) in each method's document.json."""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
for stem in sorted(p for p in root.iterdir() if p.is_dir()):
    for method in ("pdfplumber", "docling", "hybrid"):
        dj = stem / method / "01_docling" / "document.json"
        if not dj.exists():
            continue
        data = json.loads(dj.read_text(encoding="utf-8"))
        bad = []
        for i, t in enumerate(data.get("tables", [])):
            cells = t["data"]["table_cells"]
            seen, overlap = set(), 0
            for c in cells:
                for r in range(c["start_row_offset_idx"], c["end_row_offset_idx"]):
                    for k in range(c["start_col_offset_idx"], c["end_col_offset_idx"]):
                        overlap += (r, k) in seen
                        seen.add((r, k))
            if overlap:
                page = t["prov"][0]["page_no"] if t.get("prov") else None
                bad.append(f"T{i}(p{page}, {overlap} overlapping positions)")
        print(f"{stem.name[:28]:<28} {method:<11} tables={len(data.get('tables', [])):<3} overlapping={len(bad)} {' '.join(bad)}")
