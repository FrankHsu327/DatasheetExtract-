"""Regression check: hybrid scores in out/review vs the archived hybrid run in out/compare (must be identical).

  .venv-docling\\Scripts\\python.exe scripts\\regression_vs_archive.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
archive, review = ROOT / "out" / "compare", ROOT / "out" / "review"


def scores(d: Path) -> dict | None:
    ev, meta = d / "evaluate.json", d / "01_docling" / "meta.json"
    if not ev.exists():
        return None
    e = json.loads(ev.read_text(encoding="utf-8"))
    m = json.loads(meta.read_text(encoding="utf-8")).get("hybrid", {})
    f = e.get("figures") or {}
    return {"fidelity": e["stage1"]["fidelity"], "recall": e["recall"], "fig_found": f.get("found"),
            "fig_described": f.get("described"), "tables": m.get("table_sources"),
            "params_ok": sorted(r["symbol"] + "|" + str(r["conditions"]) for r in e["details"] if r["status"] == "ok")}


bad = 0
for stem in sorted(p for p in archive.iterdir() if (p / "hybrid" / "evaluate.json").exists()):
    a, b = scores(stem / "hybrid"), scores(review / stem.name / "hybrid")
    if b is None:
        print(f"MISSING  {stem.name}")
        bad += 1
        continue
    diff = {k: (a[k], b[k]) for k in a if a[k] != b[k]}
    print(f"{'SAME' if not diff else 'DIFF'}  {stem.name[:30]:<30} fidelity {b['fidelity']}  recall {b['recall']}  "
          f"figures {b['fig_found']}/{b['fig_described']}  tables {b['tables']}")
    for k, (x, y) in diff.items():
        print(f"      {k}: archive={x}  now={y}")
    bad += bool(diff)
print("REGRESSION", "PASSED (identical to archive)" if not bad else f"DIFFERENCES in {bad} datasheet(s)")
sys.exit(1 if bad else 0)
