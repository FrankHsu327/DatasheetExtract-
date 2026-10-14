"""跨 datasheet 彙整：out/compare/index.html（連到各份 compare.html）+ summary.json + summary.md。

  python -m datasheet_extractor summary [--out out/compare]
"""
from __future__ import annotations

import html
import json
from pathlib import Path

METHOD_ORDER = ["pdfplumber", "docling", "hybrid"]


def collect(root: Path) -> list[dict]:
    docs = []
    for d in sorted(p for p in root.iterdir() if (p / "compare_data.js").exists()):
        row = {"stem": d.name, "pages": len(list((d / "pages").glob("page_*.png"))), "methods": {}}
        for m in METHOD_ORDER:
            mdir = d / m
            if not (mdir / "run.json").exists():
                continue
            run = json.loads((mdir / "run.json").read_text(encoding="utf-8"))
            ev = json.loads((mdir / "evaluate.json").read_text(encoding="utf-8")) if (mdir / "evaluate.json").exists() else {}
            fig = ev.get("figures") or {}
            row["methods"][m] = {
                "label": run.get("label", m), "status": run["status"], "sec": run.get("elapsed_sec"),
                "fidelity": (ev.get("stage1") or {}).get("fidelity"), "recall": ev.get("recall"),
                "golden": ev.get("golden_count"),
                "fig_found": fig.get("found"), "fig_described": fig.get("described"), "fig_total": fig.get("golden_count"),
            }
        docs.append(row)
    return docs


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def averages(docs: list[dict]) -> dict:
    out = {}
    for m in METHOD_ORDER:
        rows = [d["methods"][m] for d in docs if m in d["methods"]]
        if not rows:
            continue
        ft = sum(r["fig_total"] or 0 for r in rows)
        out[m] = {"label": rows[0]["label"], "fidelity": _avg([r["fidelity"] for r in rows]),
                  "recall": _avg([r["recall"] for r in rows]),
                  "fig_found": sum(r["fig_found"] or 0 for r in rows) / ft if ft else None,
                  "fig_described": sum(r["fig_described"] or 0 for r in rows) / ft if ft else None,
                  "sec_per_page": _avg([(r["sec"] or 0) / d["pages"] for d in docs for mm, r in d["methods"].items()
                                        if mm == m and d["pages"]])}
    return out


def pct(x):
    return "—" if x is None else f"{x * 100:.0f}%"


def write(root: Path) -> Path:
    docs = collect(root)
    avg = averages(docs)
    (root / "summary.json").write_text(json.dumps({"datasheets": docs, "average": avg}, indent=2), encoding="utf-8")

    md = ["| Method | Table fidelity (avg) | End-to-end recall (avg) | Figures found | Figures described | s / page |",
          "|---|---|---|---|---|---|"]
    for m, a in avg.items():
        md.append(f"| {a['label']} | {pct(a['fidelity'])} | {pct(a['recall'])} | {pct(a['fig_found'])} | "
                  f"{pct(a['fig_described'])} | {a['sec_per_page']:.1f} |")
    md += ["", "| Datasheet | Method | Fidelity | Recall | Figures found | Described | Stage 1 time |", "|---|---|---|---|---|---|---|"]
    for d in docs:
        for m, r in d["methods"].items():
            md.append(f"| {d['stem'][:28]} | {r['label']} | {pct(r['fidelity'])} | {pct(r['recall'])} | "
                      f"{r['fig_found']}/{r['fig_total']} | {r['fig_described']}/{r['fig_total']} | {r['sec']} s |")
    (root / "summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    e = html.escape
    head = "".join(f"<th>{e(a['label'])}</th>" for a in avg.values())

    def cells(getter):
        return "".join(f"<td>{getter(a)}</td>" for a in avg.values())

    rows_avg = "".join(f"<tr><th>{name}</th>{cells(g)}</tr>" for name, g in [
        ("Table fidelity", lambda a: pct(a["fidelity"])), ("End-to-end recall", lambda a: pct(a["recall"])),
        ("Figures found", lambda a: pct(a["fig_found"])), ("Figures described", lambda a: pct(a["fig_described"])),
        ("Seconds / page", lambda a: f"{a['sec_per_page']:.1f}")])
    per_doc = ""
    for d in docs:
        tds = "".join(
            f"<td>{pct(r['fidelity'])} · {pct(r['recall'])}<br><small>fig {r['fig_found']}/{r['fig_total']}, "
            f"desc {r['fig_described']}/{r['fig_total']}</small></td>" if (r := d["methods"].get(m)) else "<td>—</td>"
            for m in avg)
        per_doc += f"<tr><th><a href='{e(d['stem'])}/compare.html'>{e(d['stem'])}</a><br><small>{d['pages']} pages</small></th>{tds}</tr>"
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Method Compare Summary</title><style>
:root{{--bg:#f6f7f9;--panel:#fff;--ink:#1d2330;--muted:#667085;--line:#e3e6eb;--accent:#2f6fde}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#14171c;--panel:#1c2027;--ink:#e6e8ec;--muted:#98a0ad;--line:#2c323c;--accent:#6ea0ff}}}}
:root[data-theme="dark"]{{--bg:#14171c;--panel:#1c2027;--ink:#e6e8ec;--muted:#98a0ad;--line:#2c323c;--accent:#6ea0ff}}
body{{margin:0;padding:16px;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,"Segoe UI",sans-serif}}
h1{{font-size:18px}} h2{{font-size:15px;margin-top:24px}} .wrap{{overflow-x:auto}}
table{{border-collapse:collapse;background:var(--panel);min-width:640px}} th,td{{border:1px solid var(--line);padding:6px 10px;text-align:left;vertical-align:top}}
td{{font-variant-numeric:tabular-nums}} small{{color:var(--muted)}} a{{color:var(--accent)}} p{{color:var(--muted);max-width:900px}}
</style></head><body><h1>Stage 1 method comparison</h1>
<p>Table fidelity: golden symbol + all values in one table row of the method's output (independent of extraction rules).
End-to-end recall: full pipeline extracted it with correct values. Figures: golden "Figure N" captions matched to a picture on the same page; described = the method's built-in vision model produced a description.</p>
<h2>Average over {len(docs)} datasheets</h2><div class="wrap"><table><tr><th></th>{head}</tr>{rows_avg}</table></div>
<h2>Per datasheet (fidelity · recall) — click a name to open its side-by-side viewer</h2>
<div class="wrap"><table><tr><th></th>{head}</tr>{per_doc}</table></div></body></html>"""
    (root / "index.html").write_text(page, encoding="utf-8")
    return root / "index.html"
