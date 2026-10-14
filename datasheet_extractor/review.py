"""產生 review.html：工程師只需要看被標記的項目，並可對照 Docling 截圖。

- 每張表：原始截圖（01_docling/tables/table_<i>.png）+ 正規化結果，列狀態以顏色標示
- 紅色 = unmapped（遺漏）、黃色 = 有 flag 的參數、灰色 = section/重複表頭/ignored
- 單一 HTML、無外部資源，可直接用瀏覽器開
"""
from __future__ import annotations

import html
import os
from pathlib import Path

CSS = """
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:24px;color:#1d1d1f;max-width:1400px}
h1{font-size:22px}h2{font-size:18px;margin-top:32px;border-bottom:1px solid #ddd;padding-bottom:4px}
table{border-collapse:collapse;font-size:12px;margin:8px 0}td,th{border:1px solid #ccc;padding:3px 6px;vertical-align:top}
th{background:#f2f2f2}.unmapped{background:#ffd6d6}.flagged{background:#fff3c4}.muted{color:#888;background:#f7f7f7}
.ok{background:#e8f7e8}.kv td:first-child{font-weight:600}.wrap{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start}
.wrap img{max-width:620px;border:1px solid #ccc}.flags{color:#b00;font-size:11px}.small{font-size:11px;color:#555}
.scroll{overflow-x:auto;max-width:760px}
"""

INFO_FLAGS = {"filled_down_from_merged_cell", "range_split_from_value"}


def _e(x) -> str:
    return html.escape("" if x is None else str(x))


def _val(v) -> str:
    if not v:
        return ""
    return _e(v.get("raw"))


def render(component: dict, out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    q = component["quality"]
    val = q["validation"]
    params_by_row = {p["source"]["row_id"]: p for p in component["parameters"]}
    cov_by_table = {c["table_id"]: c for c in q["coverage"]}
    xc_by_table = {c["table_id"]: c for c in (q.get("crosscheck") or [])}
    unmapped_ids = {u["row_id"] for c in q["coverage"] for u in c["unmapped_rows"]}
    status_by_row = {}
    for c in q["coverage"]:
        for u in c["unmapped_rows"]:
            status_by_row[u["row_id"]] = u["status"]

    h = [f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>Review – {_e(component['datasheet']['file'])}</title><style>{CSS}</style></head><body>"]
    h.append(f"<h1>Review: {_e(component['datasheet']['file'])}</h1>")
    h.append("<table class='kv'>")
    rows = [
        ("Part numbers", ", ".join(component["component"]["part_numbers"]) or "(not found)"),
        ("Parameters", val["parameter_count"]),
        ("Flagged parameters", val["flagged_parameters"]),
        ("Tables (extracted / total)", f"{len(q['coverage'])} / {len(component['tables'])}"),
        ("Incomplete coverage tables", ", ".join(f"{t['table_id']}({t['coverage']})" for t in val["tables_with_incomplete_coverage"]) or "none"),
        ("Expected params missing", ", ".join(val["expected"]["missing"]) or "none"),
        ("Crosscheck failed tables", ", ".join(c["table_id"] for c in (q.get("crosscheck") or []) if not c["pass"]) or "none"),
        ("Tables waiting for LLM", ", ".join(x["table_id"] for x in q.get("llm_pending", [])) or "none"),
        ("Flag counts", ", ".join(f"{k}={v}" for k, v in sorted(val["flag_count"].items())) or "none"),
    ]
    for k, v in rows:
        h.append(f"<tr><td>{_e(k)}</td><td>{_e(v)}</td></tr>")
    h.append("</table>")

    for t in component["tables"]:
        cov = cov_by_table.get(t["id"])
        xc = xc_by_table.get(t["id"])
        h.append(f"<h2 id='{_e(t['id'])}'>{_e(t['id'])} — {_e(t['caption'] or '(no caption)')}</h2>")
        meta = [f"pages {t.get('pages')}", f"category={t.get('category')}",
                f"method={t.get('extraction_method', '-')}", f"merged_from={len(t['source_refs'])} block(s)"]
        if cov:
            meta.append(f"coverage={cov['coverage']}")
        if xc:
            meta.append(f"crosscheck_recall={xc['token_recall']}")
        h.append(f"<div class='small'>{_e(' | '.join(meta))}</div>")
        if t.get("flags"):
            h.append(f"<div class='flags'>{_e('; '.join(t['flags']))}</div>")
        if xc and xc["missing_tokens"]:
            h.append(f"<div class='flags'>PDF 有但 Docling 表格沒有的數字：{_e(xc['missing_tokens'])}</div>")
        h.append("<div class='wrap'>")
        for ref in t["source_refs"]:
            idx = ref.split("/")[-1]
            img = out_dir / "01_docling" / "tables" / f"table_{idx}.png"
            if img.exists():
                h.append(f"<img src='{_e(os.path.relpath(img, out_dir))}' alt='{_e(ref)}'>")
        h.append("<div class='scroll'><table><tr><th>row_id</th>")
        for c in t["columns"]:
            h.append(f"<th>{_e(c['header'])}<br><span class='small'>{_e(c['role'])}</span></th>")
        h.append("<th>status / flags</th></tr>")
        for row in t["rows"]:
            if row["kind"] == "empty":
                continue
            rid = row["row_id"]
            p = params_by_row.get(rid)
            flags = [f for f in (p["flags"] if p else []) if f.split(":")[0] not in INFO_FLAGS]
            if rid in unmapped_ids:
                cls, note = "unmapped", status_by_row.get(rid, "unmapped")
            elif p and flags:
                cls, note = "flagged", "; ".join(flags)
            elif p:
                cls, note = "ok", p["method"]
            else:
                cls, note = "muted", row["kind"]
            h.append(f"<tr class='{cls}'><td>{_e(rid)}</td>" +
                     "".join(f"<td>{_e(c)}</td>" for c in row["cells"]) + f"<td>{_e(note)}</td></tr>")
        h.append("</table></div></div>")
        if t.get("footnotes"):
            h.append("<div class='small'>Notes: " + _e(" | ".join(f"({k}) {v}" for k, v in t["footnotes"].items())) + "</div>")

    h.append("<h2>Figures</h2><table><tr><th>id</th><th>page</th><th>kind</th><th>caption</th><th>linked</th><th>flags</th></tr>")
    for f in component["figures"]:
        cls = "flagged" if f.get("needs_review") or f.get("flags") else ""
        page = f["provenance"][0]["page"] if f["provenance"] else ""
        h.append(f"<tr class='{cls}'><td>{_e(f['id'])}</td><td>{_e(page)}</td><td>{_e(f['kind'])}</td>"
                 f"<td>{_e(f['caption'])}</td><td>{_e(', '.join(f.get('linked_parameters', [])))}</td>"
                 f"<td>{_e('; '.join(f.get('flags', [])))}</td></tr>")
    h.append("</table></body></html>")
    path = out_dir / "review.html"
    path.write_text("\n".join(h), encoding="utf-8")
    return path
