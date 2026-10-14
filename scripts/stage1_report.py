"""Print non-ok Stage 1 fidelity rows for each method (debug the metric / see what each method lost)."""
import json
import sys
from pathlib import Path

d = Path(sys.argv[1])
for m in sorted(p for p in d.iterdir() if (p / "evaluate.json").exists()):
    ev = json.loads((m / "evaluate.json").read_text(encoding="utf-8"))
    s1 = ev["stage1"]
    print(f"== {m.name}: fidelity {s1['fidelity']} {s1['status_count']}  e2e {ev['recall']} {ev['status_count']}")
    for det, e2e in zip(s1["details"], ev["details"]):
        if det["status"] != "ok" or (len(sys.argv) > 2 and e2e["status"] != "ok"):
            print(f"   {det['symbol']:<10} {str(det['conditions'] or ''):<40} s1={det['status']:<8} e2e={e2e['status']}")
