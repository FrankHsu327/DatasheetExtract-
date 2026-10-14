"""Stage 1：hybrid = Docling 找位置 + pdfplumber 取文字 + Granite Vision 描述圖（本專案唯一的 Stage 1）。

為什麼：方法比較（docs/METHOD_COMPARISON.md，pdfplumber／Docling 單獨使用的程式已移除，結果保留在 out/compare）顯示
- pdfplumber 讀表最準（文字層逐字），但只認得框線表格、不會找圖；
- Docling 找表格與圖的位置最穩（含無框線表格），但 TableFormer 的格子常錯（合併儲存格、子表頭消失、數值空白）；
- Granite Vision 用 Docling 預設 prompt 描述圖，內容很空泛。

做法
1. Docling 標準流程（layout + TableFormer + 圖片分類），不跑 Docling 內建的圖片描述。
2. 表格：Docling 偵測到的每張表
   a. 表格範圍內有框線 → pdfplumber 依框線重建（結構與文字都來自 PDF）              source = pdfplumber_lines
   b. 沒有框線     → 用 Docling 的列／欄位置當格線，把 pdfplumber 的字依座標放進去  source = docling_grid
   兩種都和 Docling 原本的數字 token 比對，差異大 → meta.json 記 disagreement（review 用）。
   另外：頁面上有框線、但 Docling 沒偵測到的表，用 pdfplumber 補進來                source = pdfplumber_added
3. 圖：Docling 找到的圖，以 Granite Vision + datasheet 專用 prompt 描述；prompt 帶入 caption 與
   pdfplumber 從圖範圍內讀到的文字（腳位名稱、訊號名稱），讓描述用正確名稱，不靠模型讀小字。

輸出：<out>/01_docling/document.json（DoclingDocument 格式）→ Stage 2+ 的唯一輸入。
"""
from __future__ import annotations

import gc
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from .docling_reader import DoclingDoc
from .text_normalize import normalize_text, numeric_tokens

BBox = tuple[float, float, float, float]   # (l, t, r, b) top-left origin, PDF points


# ------------------------------------------------------------------ geometry
def _area(b: BBox) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _inter(a: BBox, b: BBox) -> float:
    return _area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))


def _clip(b: BBox, w: float, h: float, pad: float = 0.0) -> BBox:
    return (max(0.0, b[0] - pad), max(0.0, b[1] - pad), min(w, b[2] + pad), min(h, b[3] + pad))


# ------------------------------------------------------------------ tables
def _ruled_table(page, box: BBox, cfg: dict):
    """pdfplumber 依框線在 Docling 表格範圍內找表；涵蓋率不足或太空 → None。"""
    from .pdf_ruled_tables import table_to_cells

    hcfg = cfg["hybrid"]
    crop = page.crop(_clip(box, float(page.width), float(page.height), pad=3), strict=False)
    best, best_cov = None, 0.0
    for t in crop.find_tables():
        cov = _inter(t.bbox, box) / max(_area(box), 1e-6)
        if cov > best_cov:
            best, best_cov = t, cov
    if best is None or best_cov < float(hcfg.get("lines_min_coverage", 0.6)):
        return None
    nrows, ncols, cells = table_to_cells(page, best, float(hcfg.get("y_tolerance", 4)))
    filled = sum(1 for c in cells if c["text"]) / max(1, len(cells))
    if nrows < 2 or ncols < 2 or filled < float(hcfg.get("lines_min_filled_ratio", 0.25)):
        return None
    return best, nrows, ncols, cells


def _bands(cells: list[dict], n: int, lo_key: str, hi_key: str, start: str, end: str, outer: tuple[float, float]):
    """Docling 每一欄（列）的範圍 → 相鄰兩欄的中點當邊界。回傳 n+1 個邊界。"""
    lo: list[float | None] = [None] * n
    hi: list[float | None] = [None] * n
    for c in cells:
        bb = c.get("bbox")
        if not bb:
            continue
        s, e = int(c[start]), int(c[end]) - 1
        lo[s] = bb[lo_key] if lo[s] is None else min(lo[s], bb[lo_key])
        hi[e] = bb[hi_key] if hi[e] is None else max(hi[e], bb[hi_key])
    edges = [outer[0]]
    for i in range(n - 1):
        a, b = hi[i], lo[i + 1]
        if a is not None and b is not None:
            edges.append((a + b) / 2)
        elif a is not None:
            edges.append(a + 1)
        elif b is not None:
            edges.append(b - 1)
        else:   # 整欄都沒有 bbox：在前後已知邊界間平均分配
            edges.append(None)
    edges.append(outer[1])
    known = [i for i, v in enumerate(edges) if v is not None]
    for i, v in enumerate(edges):
        if v is None:
            p = max(k for k in known if k < i)
            q = min(k for k in known if k > i)
            edges[i] = edges[p] + (edges[q] - edges[p]) * (i - p) / (q - p)
    return edges


def _grid_fill(page, table: dict, box: BBox, cfg: dict) -> list[dict] | None:
    """沿用 Docling 的格子（含合併儲存格），每格文字改成 pdfplumber 在該格範圍內的字。"""
    data = table.get("data") or {}
    cells = data.get("table_cells") or []
    nr, nc = int(data.get("num_rows") or 0), int(data.get("num_cols") or 0)
    if not cells or not nr or not nc:
        return None
    xs = _bands(cells, nc, "l", "r", "start_col_offset_idx", "end_col_offset_idx", (box[0], box[2]))
    ys = _bands(cells, nr, "t", "b", "start_row_offset_idx", "end_row_offset_idx", (box[1], box[3]))
    y_tol = float(cfg["hybrid"].get("y_tolerance", 4))
    words = page.crop(_clip(box, float(page.width), float(page.height), pad=1), strict=False).extract_words(
        x_tolerance=3, y_tolerance=y_tol, keep_blank_chars=False)
    slot: dict[tuple[int, int], list[dict]] = {}
    for w in words:
        cx, cy = (w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2
        c = next((i for i in range(nc) if xs[i] <= cx < xs[i + 1]), None)
        r = next((i for i in range(nr) if ys[i] <= cy < ys[i + 1]), None)
        if c is not None and r is not None:
            slot.setdefault((r, c), []).append(w)
    out = []
    for cell in cells:
        ws = [w for r in range(int(cell["start_row_offset_idx"]), int(cell["end_row_offset_idx"]))
              for c in range(int(cell["start_col_offset_idx"]), int(cell["end_col_offset_idx"])) for w in slot.get((r, c), [])]
        ws.sort(key=lambda w: (round(w["top"] / y_tol), w["x0"]))
        new = dict(cell)
        new["text"] = " ".join(w["text"] for w in ws)
        out.append(new)
    return out


def _cells_from_ruled(ruled, page_h: float) -> tuple[int, int, list[dict]]:
    from .pdf_ruled_tables import header_rows

    _t, nrows, ncols, cells = ruled
    n_hdr = header_rows(cells, nrows)
    return nrows, ncols, [{
        "bbox": {"l": c["bbox"][0], "t": c["bbox"][1], "r": c["bbox"][2], "b": c["bbox"][3], "coord_origin": "TOPLEFT"},
        "row_span": c["r1"] - c["r0"], "col_span": c["c1"] - c["c0"],
        "start_row_offset_idx": c["r0"], "end_row_offset_idx": c["r1"],
        "start_col_offset_idx": c["c0"], "end_col_offset_idx": c["c1"],
        "text": c["text"], "column_header": c["r0"] < n_hdr, "row_header": False, "row_section": False,
    } for c in cells]


def _num_tokens(cells: list[dict]) -> Counter:
    tok: Counter = Counter()
    for c in cells:
        tok.update(numeric_tokens(normalize_text(c.get("text") or "")))
    return tok


def _disagreement(a: Counter, b: Counter) -> float:
    n = max(sum(a.values()), sum(b.values()))
    return round(sum(((a - b) + (b - a)).values()) / n, 3) if n else 0.0


def _rebuild_tables(data: dict, pdf, cfg: dict) -> list[dict]:
    doc = DoclingDoc(data)
    report = []
    ratio = float(cfg["hybrid"].get("disagreement_ratio", 0.1))
    for i, t in enumerate(data.get("tables", [])):
        prov = (t.get("prov") or [None])[0]
        if not prov:
            continue
        pno = int(prov["page_no"])
        page = pdf.pages[pno - 1]
        box = doc.bbox_topleft(prov)
        before = _num_tokens(t["data"].get("table_cells") or [])
        ruled = _ruled_table(page, box, cfg)
        if ruled is not None:
            nrows, ncols, cells = _cells_from_ruled(ruled, float(page.height))
            source = "pdfplumber_lines"
        else:
            cells = _grid_fill(page, t, box, cfg)
            if cells is None:
                report.append({"table": i, "page": pno, "source": "docling_unchanged"})
                continue
            nrows, ncols = int(t["data"]["num_rows"]), int(t["data"]["num_cols"])
            source = "docling_grid"
        t["data"] = {"table_cells": cells, "num_rows": nrows, "num_cols": ncols}
        dis = _disagreement(before, _num_tokens(cells))
        report.append({"table": i, "page": pno, "source": source, "rows": nrows, "cols": ncols,
                       "numeric_disagreement_vs_docling": dis, "flag": dis > ratio})
    return report


def _add_missed_ruled_tables(data: dict, pdf, cfg: dict) -> list[dict]:
    """Docling 沒偵測到、但 pdfplumber 依框線找得到的表 → 補進 document（依頁面位置插入閱讀順序）。"""
    from docling_core.types.doc import (BoundingBox, CoordOrigin, DoclingDocument, ProvenanceItem, TableCell,
                                        TableData)

    doc = DoclingDoc(data)
    have: dict[int, list[BBox]] = {}
    for t in data.get("tables", []):
        for p in t.get("prov") or []:
            have.setdefault(int(p["page_no"]), []).append(doc.bbox_topleft(p))
    for p in data.get("pictures", []):   # 框線圖（timing diagram）常被 pdfplumber 當成表；Docling 判成圖的就不補
        for pv in p.get("prov") or []:
            have.setdefault(int(pv["page_no"]), []).append(doc.bbox_topleft(pv))
    found = []
    for pno, page in enumerate(pdf.pages, start=1):
        for t in page.find_tables():
            if any(_inter(t.bbox, b) / max(_area(t.bbox), 1e-6) > 0.3 for b in have.get(pno, [])):
                continue
            ruled = _ruled_table(page, t.bbox, cfg)
            if ruled is not None:
                found.append((pno, t.bbox, ruled))
    if not found:
        return []
    ddoc = DoclingDocument.model_validate(data)
    added = []
    for pno, bb, ruled in found:
        H = float(pdf.pages[pno - 1].height)
        nrows, ncols, cells = _cells_from_ruled(ruled, H)
        tcells = [TableCell(**{k: v for k, v in c.items() if k != "bbox"},
                            bbox=BoundingBox(l=c["bbox"]["l"], t=c["bbox"]["t"], r=c["bbox"]["r"], b=c["bbox"]["b"],
                                             coord_origin=CoordOrigin.TOPLEFT)) for c in cells]
        item = ddoc.add_table(data=TableData(num_rows=nrows, num_cols=ncols, table_cells=tcells),
                              prov=ProvenanceItem(page_no=pno, charspan=(0, 0), bbox=BoundingBox(
                                  l=bb[0], t=H - bb[1], r=bb[2], b=H - bb[3], coord_origin=CoordOrigin.BOTTOMLEFT)))
        _move_to_reading_position(ddoc, item, pno, bb[1])
        added.append({"page": pno, "source": "pdfplumber_added", "rows": nrows, "cols": ncols})
    data.clear()
    data.update(ddoc.export_to_dict())
    return added


def _move_to_reading_position(ddoc, item, pno: int, top: float) -> None:
    """add_table 會接在 body 最後；移到同一頁中位置在它上方的最後一個項目之後。"""
    children = ddoc.body.children
    ref = next(c for c in children if c.cref == item.self_ref)
    children.remove(ref)
    pos = 0
    for i, c in enumerate(children):
        node = c.resolve(ddoc)
        prov = getattr(node, "prov", None)
        if not prov:
            continue
        p = prov[0]
        H = ddoc.pages[p.page_no].size.height
        t = p.bbox.to_top_left_origin(page_height=H).t
        if p.page_no < pno or (p.page_no == pno and t <= top):
            pos = i + 1
    children.insert(pos, ref)


# ------------------------------------------------------------------ figures
def _describe_pictures(data: dict, pdf, source: Path, cfg: dict) -> dict:
    import pypdfium2 as pdfium

    from .figures import picture_class
    from .model_env import ROOT
    from .vision_describe import GraniteVision

    hcfg = cfg["hybrid"]
    tpl = (ROOT / hcfg.get("describe_prompt_file", "prompts/figure_describe_hybrid.md")).read_text(encoding="utf-8")
    skip = set(hcfg.get("describe_skip_classes") or [])
    min_area = float(hcfg.get("describe_min_area", 0.02))
    scale = float(hcfg.get("describe_image_scale", 2.0))
    top_band, bottom_band = float(hcfg.get("header_margin", 75)), float(hcfg.get("footer_margin", 60))
    doc = DoclingDoc(data)
    todo = []
    for p in data.get("pictures", []):
        prov = (p.get("prov") or [None])[0]
        if not prov or p.get("content_layer") == "furniture":
            continue
        pno = int(prov["page_no"])
        W, H = doc.page_size(pno)
        box = _clip(doc.bbox_topleft(prov), W, H)
        # 頁首／頁尾的 logo 條（Winbond 每頁上方的色條會被分類成 bar_chart）不是內容
        in_band = box[3] <= top_band or box[1] >= H - bottom_band
        if in_band or _area(box) / (W * H) < min_area or picture_class(p) in skip:
            continue
        todo.append((p, pno, box))
    stats = {"pictures": len(data.get("pictures", [])), "described": 0, "describe_sec": 0.0}
    if not todo:
        return stats
    t0 = time.time()
    vlm = GraniteVision()
    rendered: dict[int, Any] = {}
    pdoc = pdfium.PdfDocument(str(source))
    for p, pno, box in todo:
        if pno not in rendered:
            rendered = {pno: pdoc[pno - 1].render(scale=scale).to_pil()}   # 只留目前這頁，省記憶體
        img = rendered[pno].crop(tuple(int(v * scale) for v in box))
        page = pdf.pages[pno - 1]
        pdf_text = " ".join((page.crop(box, strict=False).extract_text(x_tolerance=2) or "").split())[:1200]
        prompt = (tpl.replace("{{CAPTION}}", normalize_text(doc.caption_text(p)) or "(none)")
                  .replace("{{PDF_TEXT}}", pdf_text or "(none)"))
        text = vlm.describe(img, prompt, int(hcfg.get("describe_max_new_tokens", 400)))
        meta = p.get("meta") or {}
        meta["description"] = {"text": text, "created_by": "granite-vision-3.3-2b (hybrid prompt)"}
        p["meta"] = meta
        stats["described"] += bool(text)
    pdoc.close()
    vlm.close()
    stats["describe_sec"] = round(time.time() - t0, 1)
    return stats


# ------------------------------------------------------------------ entry
def convert_hybrid(source: str | Path, out_dir: str | Path, cfg: dict) -> Path:
    import pdfplumber
    from docling.datamodel.base_models import ConversionStatus
    from docling_core.types.doc import DoclingDocument

    from .docling_layout import build_converter, save_result

    source = Path(source)
    out = Path(out_dir) / "01_docling"
    t0 = time.time()

    # 1) Docling：layout + TableFormer + 圖片分類；圖片描述由下面的 Granite Vision（帶 PDF 文字的 prompt）負責
    converter, opts = build_converter(cfg)
    result = converter.convert(str(source), raises_on_error=False)
    if result.status not in (ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS):
        raise RuntimeError(f"Docling conversion failed: {result.status} {getattr(result, 'errors', '')}")
    save_result(result, source, out, opts, time.time() - t0, backend="hybrid")
    del converter, result
    gc.collect()
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass
    t_docling = time.time() - t0

    data = json.loads((out / "document.json").read_text(encoding="utf-8"))
    with pdfplumber.open(str(source)) as pdf:
        # 2) 表格
        t1 = time.time()
        tables = _rebuild_tables(data, pdf, cfg)
        added = _add_missed_ruled_tables(data, pdf, cfg) if cfg["hybrid"].get("add_missed_ruled_tables", True) else []
        t_tables = time.time() - t1
        (out / "document.md").write_text(DoclingDocument.model_validate(data).export_to_markdown(), encoding="utf-8")
        # 3) 圖
        fig = _describe_pictures(data, pdf, source, cfg) if cfg["hybrid"].get("describe", True) else {}

    (out / "document.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    meta["elapsed_sec"] = round(time.time() - t0, 2)
    meta["hybrid"] = {
        "docling_sec": round(t_docling, 1), "tables_sec": round(t_tables, 1),
        "tables": tables + added,
        "table_sources": dict(Counter(t["source"] for t in tables + added)),
        "tables_flagged": [t for t in tables if t.get("flag")],
        "figures": fig,
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return out / "document.json"
