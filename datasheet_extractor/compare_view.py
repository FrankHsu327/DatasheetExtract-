"""產生 compare.html：左側為某個方法的輸出（逐頁），右側為原始 PDF 頁面。

完全離線：頁面圖用 pypdfium2 預先渲染成 PNG，資料寫成 compare_data.js（file:// 也能開）。

out/compare/<stem>/
  compare.html
  compare_data.js
  pages/page_N.png
  <method>/01_docling/document.json ...   各方法的完整 pipeline 輸出
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .docling_reader import DoclingDoc
from .figures import picture_class, picture_description
from .text_normalize import normalize_text

_TEXT_KIND = {"section_header": "heading", "title": "heading", "caption": "caption", "list_item": "list",
              "footnote": "footnote", "formula": "formula", "code": "code"}


def render_pages(pdf: Path, out_dir: Path, scale: float = 2.0) -> list[dict]:
    """Render every page to PNG once. Returns [{page, width, height, img}] (width/height in PDF points)."""
    import pypdfium2 as pdfium

    out_dir.mkdir(parents=True, exist_ok=True)
    pages = []
    pdf_doc = pdfium.PdfDocument(str(pdf))
    for i in range(len(pdf_doc)):
        page = pdf_doc[i]
        w, h = page.get_size()
        name = f"page_{i + 1}.png"
        target = out_dir / name
        if not target.exists():
            page.render(scale=scale).to_pil().save(target)
        pages.append({"page": i + 1, "width": round(w, 2), "height": round(h, 2), "img": f"pages/{name}"})
    pdf_doc.close()
    return pages


def _table_html(table: dict) -> str:
    data = table.get("data") or {}
    cells = data.get("table_cells") or []
    if not cells:
        return "<table><tr><td><i>(empty table)</i></td></tr></table>"
    rows: dict[int, list[dict]] = {}
    for c in cells:
        rows.setdefault(int(c["start_row_offset_idx"]), []).append(c)
    parts = ["<table>"]
    for r in sorted(rows):
        parts.append("<tr>")
        for c in sorted(rows[r], key=lambda c: int(c["start_col_offset_idx"])):
            tag = "th" if c.get("column_header") else "td"
            rs = int(c["end_row_offset_idx"]) - int(c["start_row_offset_idx"])
            cs = int(c["end_col_offset_idx"]) - int(c["start_col_offset_idx"])
            span = (f' rowspan="{rs}"' if rs > 1 else "") + (f' colspan="{cs}"' if cs > 1 else "")
            parts.append(f"<{tag}{span}>{html.escape(normalize_text(c.get('text') or ''))}</{tag}>")
        parts.append("</tr>")
    parts.append("</table>")
    return "".join(parts)


def doc_items(docling_json: Path) -> list[dict]:
    """Flatten a DoclingDocument into reading-order items with page + top-left bbox."""
    doc = DoclingDoc.load(docling_json)
    items: list[dict] = []
    for it in doc.iter_body():
        ref = it.get("self_ref", "")
        prov = doc.provenance(it)
        page = prov[0]["page"] if prov else None
        bbox = prov[0]["bbox"] if prov else None
        # 顯示用文字套用與 pipeline 相同的正規化（VLM 後端的 LaTeX symbol → 純文字）
        if ref.startswith("#/tables"):
            entry = {"kind": "table", "html": _table_html(it), "caption": normalize_text(doc.caption_text(it))}
        elif ref.startswith("#/pictures"):
            entry = {"kind": "picture", "caption": normalize_text(doc.caption_text(it)),
                     "text": " ".join(doc.child_texts(it))[:400],
                     "description": picture_description(it), "class": picture_class(it)}
        else:
            label = it.get("label", "text")
            entry = {"kind": _TEXT_KIND.get(label, "text"), "text": normalize_text(it.get("text", ""))}
            if label in ("page_header", "page_footer"):
                continue
        entry.update({"page": page, "bbox": bbox, "ref": ref})
        items.append(entry)
    return items


def _params(component: dict | None) -> list[dict]:
    tables = {t["id"]: t for t in (component or {}).get("tables", [])}
    out = []
    for p in (component or {}).get("parameters", []):
        src = p.get("source") or {}
        pages = src.get("pages") or []
        tprov = (tables.get(src.get("table_id")) or {}).get("provenance") or []
        tbox = next((pv.get("bbox") for pv in tprov if pages and pv.get("page") == pages[0]), None)

        def raw(k):
            v = p.get(k)
            return v.get("raw") if isinstance(v, dict) else None
        out.append({"name": p.get("name"), "symbol": p.get("symbol"), "conditions": p.get("conditions"),
                    "min": raw("min"), "typ": raw("typ"), "max": raw("max"), "value": raw("value"),
                    "unit": p.get("unit"), "flags": p.get("flags", []), "table": src.get("table_id"),
                    "page": pages[0] if pages else None, "bbox": tbox})
    return out


def build(stem_dir: Path, pdf: Path, methods: list[dict], golden: dict | None = None) -> Path:
    """methods: [{id, label, status, elapsed_sec, error, raw_md}] — each stem_dir/<id>/ holds pipeline output."""
    pages = render_pages(pdf, stem_dir / "pages")
    data: dict[str, Any] = {"pdf": pdf.name, "pages": pages, "methods": [], "golden": golden}
    for m in methods:
        mdir = stem_dir / m["id"]
        dj = mdir / "01_docling" / "document.json"
        comp_files = list(mdir.glob("*.component.json"))
        component = json.loads(comp_files[0].read_text(encoding="utf-8")) if comp_files else None
        entry = dict(m)
        entry["items"] = doc_items(dj) if dj.exists() else []
        entry["parameters"] = _params(component)
        if component:
            q = component["quality"]
            entry["stats"] = {
                "tables": len(component.get("tables", [])),
                "parameters": len(component.get("parameters", [])),
                "flagged": q["validation"].get("flagged_parameters"),
                "expected_missing": q["expected_parameters"].get("missing", []),
                "coverage_min": min([c["coverage"] for c in q["coverage"]], default=None),
            }
        ev = mdir / "evaluate.json"
        if ev.exists():
            entry["evaluate"] = json.loads(ev.read_text(encoding="utf-8"))
        data["methods"].append(entry)
    (stem_dir / "compare_data.js").write_text(
        "window.COMPARE = " + json.dumps(data, ensure_ascii=False, default=str) + ";", encoding="utf-8")
    src = Path(__file__).with_name("compare_template.html")
    (stem_dir / "compare.html").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return stem_dir / "compare.html"
