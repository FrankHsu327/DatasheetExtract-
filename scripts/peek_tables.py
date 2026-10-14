"""Print spec-section tables (pages 61-66) of a method's 02_tables/tables.json for debugging."""
import json
import sys
from pathlib import Path

d = Path(sys.argv[1])
pages = range(int(sys.argv[2]), int(sys.argv[3]) + 1) if len(sys.argv) > 3 else range(61, 67)
tables = json.loads((d / "02_tables" / "tables.json").read_text(encoding="utf-8"))
for t in tables:
    if not set(t.get("pages", [])) & set(pages):
        continue
    print(f"=== {t['id']} p{t.get('pages')} cat={t.get('category')} spec_like={t.get('spec_like')} cap={t.get('caption')!r}")
    print("  headers:", t.get("header_texts"))
    print("  columns:", [(c.get("role"), c.get("header")) for c in t.get("columns", [])])
    print("  flags:", t.get("flags"))
    for r in t["rows"][:6]:
        print("   ", r["kind"], r["cells"])
    print("   ... rows:", len(t["rows"]))
