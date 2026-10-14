"""雙路比對：用 pdfplumber 讀 PDF 文字層，檢查 Docling 表格是否漏了儲存格。

方法：在每張表格的 bbox 內取出 PDF 文字層所有「數字 token」，與 Docling 表格儲存格內的數字 token
做 multiset 比對。PDF 有但 Docling 沒有的 token = 疑似遺漏（TableFormer 漏格/錯併、或表格被截斷）。

- 不依賴表格格線（無格線表格也適用）
- 只適用有文字層的數位 PDF；掃描檔需改用 OCR 結果或視覺 LLM 比對
- TODO(Devin)【可選】第三路：把 tables/table_<i>.png 丟給公司視覺 LLM 轉錄，再與 Docling 結果逐格比對
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .text_normalize import normalize_text, numeric_tokens


def _docling_tokens(table: dict, pages_bbox: tuple[int, list[float]] | None = None) -> Counter:
    c: Counter = Counter()
    for h in table["header_texts"]:
        c.update(numeric_tokens(h))
    for row in table["rows"]:
        for i, cell in enumerate(row["cells"]):
            if i in row.get("filled", []):
                continue  # fill-down 複製的不算
            c.update(numeric_tokens(cell))
    if table.get("caption"):
        c.update(numeric_tokens(table["caption"]))
    return c


def crosscheck_tables(pdf_path: str | Path, tables: list[dict], cfg: dict, pad: float = 1.5) -> list[dict[str, Any]]:
    import pdfplumber

    results = []
    min_recall = float(cfg["crosscheck"].get("min_token_recall", 0.98))
    with pdfplumber.open(str(pdf_path)) as pdf:
        for t in tables:
            pdf_tokens: Counter = Counter()
            # 同一張表合併前的每個 Docling 區塊都有自己的 bbox
            for prov in t["provenance"]:
                page_idx = prov["page"] - 1
                if page_idx < 0 or page_idx >= len(pdf.pages):
                    continue
                page = pdf.pages[page_idx]
                l, top, r, b = prov["bbox"]
                box = (max(0, l - pad), max(0, top - pad), min(page.width, r + pad), min(page.height, b + pad))
                if box[2] <= box[0] or box[3] <= box[1]:
                    continue  # bbox 完全落在頁面外（VLM 後端偶爾會給出超出頁面的座標）
                words =page.within_bbox(box).extract_words(keep_blank_chars=False, use_text_flow=True)
                for w in words:
                    pdf_tokens.update(numeric_tokens(w["text"]))
            dl_tokens = _docling_tokens(t)
            missing = pdf_tokens - dl_tokens
            extra = dl_tokens - pdf_tokens
            total = sum(pdf_tokens.values())
            recall = 1.0 if total == 0 else round(1 - sum(missing.values()) / total, 4)
            res = {"table_id": t["id"], "caption": t.get("caption"), "pages": t.get("pages"),
                   "pdf_numeric_tokens": total, "token_recall": recall,
                   "missing_tokens": dict(missing.most_common(50)),
                   "extra_tokens": dict(extra.most_common(20)),
                   "pass": recall >= min_recall}
            if not res["pass"]:
                t["flags"].append(f"crosscheck_low_recall:{recall}")
            results.append(res)
    return results


def find_untabled_numeric_regions(pdf_path: str | Path, tables: list[dict], min_lines: int = 4,
                                  max_line_gap: float = 24.0, exclude_boxes: list[dict] | None = None) -> list[dict]:
    """找出「連續多行都有獨立數字、但不在任何 Docling 表格內」的區域 → 疑似整張表沒被偵測到（Layout 層遺漏）。

    判斷：表格外的文字依 y 座標分行；含「規格值 token」（帶小數或單位）的行若連續出現 ≥ min_lines 行（行距 < max_line_gap），
    就視為疑似表格。段落中偶爾出現的數字（例如 caption 的 -40 to 85 °C）只有一行，不會觸發。
    """
    import pdfplumber
    import re as _re

    from .text_normalize import spec_value_tokens
    covered: dict[int, list[list[float]]] = {}
    for t in tables:
        for p in t["provenance"]:
            covered.setdefault(p["page"], []).append(p["bbox"])
    for p in exclude_boxes or []:                  # 例如 figure 範圍（時序圖上的數字不是表格）
        covered.setdefault(p["page"], []).append(p["bbox"])
    out = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            lines: dict[int, list] = {}
            for w in page.extract_words():
                cx, cy = (w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2
                if any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in covered.get(i, [])):
                    continue
                lines.setdefault(int(round(w["top"] / 3.0)), []).append(w)
            numeric_lines = sorted(
                (min(w["top"] for w in ws), ws) for ws in lines.values()
                if spec_value_tokens(" ".join(w["text"] for w in sorted(ws, key=lambda w: w["x0"]))))
            run: list = []
            for top, ws in numeric_lines + [(float("inf"), [])]:
                if run and top - run[-1][0] > max_line_gap:
                    if len(run) >= min_lines:
                        out.append({"page": i, "y_range": [round(run[0][0], 1), round(run[-1][0] + 10, 1)],
                                    "numeric_lines": len(run),
                                    "sample": " | ".join(" ".join(w["text"] for w in r[1])[:60] for r in run[:4])})
                    run = []
                if ws:
                    run.append((top, ws))
    return out
