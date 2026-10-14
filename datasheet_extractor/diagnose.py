"""診斷：不需要 golden set，直接從 Docling 輸出找「可疑遺漏」。

檢查項目
- 每頁 Docling 偵測到的 table / picture / text 數量
- 每張表：列數、欄數、表頭列數、空白格比例、是否有 caption
- 文字段落內數字密度很高 → 疑似表格被當成 text（Layout 層遺漏）
- caption 以 "Table" 開頭的 picture → 疑似表格被當成圖
- （有 PDF 時）PDF 文字層數字密集、但不在任何 Docling 表格 bbox 內的區域
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .docling_reader import DoclingDoc, table_grid
from .text_normalize import normalize_text, numeric_tokens, spec_value_tokens


def diagnose(doc: DoclingDoc, pdf_path: str | Path | None = None, norm_tables: list[dict] | None = None,
             numeric_text_threshold: int = 5, region_min_lines: int = 4) -> dict[str, Any]:
    pages: dict[int, dict[str, int]] = {}
    tables_info, suspects = [], []
    picture_boxes: list[dict] = []

    def bump(page: int, key: str):
        pages.setdefault(page, {"tables": 0, "pictures": 0, "texts": 0})[key] += 1

    for item in doc.iter_body():
        ref = item.get("self_ref", "")
        provs = doc.provenance(item)
        page = provs[0]["page"] if provs else 0
        if ref.startswith("#/tables"):
            bump(page, "tables")
            grid, meta = table_grid(item)
            n_cells = sum(len(r) for r in grid) or 1
            empty = sum(1 for r in grid for c in r if not c.strip())
            hdr = sum(1 for r, row in enumerate(grid) if row and all(meta[r][i]["column_header"]
                                                                       for i, c in enumerate(row) if c.strip()))
            info = {"ref": ref, "page": page, "rows": len(grid), "cols": len(grid[0]) if grid else 0,
                    "header_rows_flagged": hdr, "empty_cell_ratio": round(empty / n_cells, 3),
                    "caption": normalize_text(doc.caption_text(item)) or None}
            if info["empty_cell_ratio"] > 0.5:
                suspects.append({"type": "table_mostly_empty", **info})
            if info["rows"] <= 1:
                suspects.append({"type": "table_single_row", **info})
            tables_info.append(info)
        elif ref.startswith("#/pictures"):
            bump(page, "pictures")
            picture_boxes.extend(provs)
            cap = normalize_text(doc.caption_text(item))
            if cap.lower().startswith("table"):
                suspects.append({"type": "table_as_picture", "ref": ref, "page": page, "caption": cap})
        else:
            bump(page, "texts")
            text = item.get("text", "")
            n = len(spec_value_tokens(text))
            if n >= numeric_text_threshold and item.get("label") not in ("caption",):
                suspects.append({"type": "numeric_dense_text", "ref": ref, "page": page,
                                 "numeric_tokens": n, "sample": normalize_text(text)[:160]})

    report: dict[str, Any] = {
        "document": doc.name,
        "totals": {"tables_raw": len(tables_info), "pictures": sum(p["pictures"] for p in pages.values()),
                   "pages_with_content": len(pages)},
        "pages": {str(k): v for k, v in sorted(pages.items())},
        "tables": tables_info,
        "suspects": suspects,
    }
    if norm_tables is not None:
        report["normalized_tables"] = [
            {"id": t["id"], "pages": t.get("pages"), "rows": len(t["rows"]), "caption": t.get("caption"),
             "category": t.get("category"), "roles": [c["role"] for c in t["columns"]],
             "flags": t.get("flags"), "merged_from": t.get("source_refs")} for t in norm_tables]
    if pdf_path and norm_tables is not None:
        from .crosscheck import find_untabled_numeric_regions
        regions = find_untabled_numeric_regions(pdf_path, norm_tables, min_lines=region_min_lines,
                                                exclude_boxes=picture_boxes)
        report["untabled_numeric_regions"] = regions
        for r in regions:
            suspects.append({"type": "numeric_region_outside_tables", **r})
    report["suspect_count"] = len(suspects)
    return report
