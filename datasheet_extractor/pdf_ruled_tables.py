"""pdfplumber 依框線重建表格（hybrid 用）：儲存格座標 → row/col span、儲存格文字、表頭列數。

- 表格：pdfplumber 依框線找到的格子，依座標還原 row/col span；文字取自 PDF 文字層。
- 表頭：以粗體判斷（或整列都是 MIN/TYP/MAX 類字詞）。
- 下標：用 y_tolerance 把下標字合併回主字（F_R、C_IN）。
"""
from __future__ import annotations

_HEADER_WORDS = {"min", "typ", "max", "typical", "nom", "minimum", "maximum", "spec", "limits", "unit", "units"}


def _is_bold(chars: list[dict]) -> bool:
    if not chars:
        return False
    bold = sum(1 for c in chars if "bold" in c.get("fontname", "").lower())
    return bold / len(chars) > 0.6


def _boundaries(values: list[float], tol: float = 1.5) -> list[float]:
    out: list[float] = []
    for v in sorted(values):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def _idx(bounds: list[float], v: float) -> int:
    return min(range(len(bounds)), key=lambda i: abs(bounds[i] - v))


def table_to_cells(page, table, y_tol: float) -> tuple[int, int, list[dict]]:
    """pdfplumber Table → (num_rows, num_cols, cells)；cell = {r0, r1, c0, c1, bbox, text, bold}。"""
    cells = table.cells
    xs = _boundaries([c[0] for c in cells] + [c[2] for c in cells])
    ys = _boundaries([c[1] for c in cells] + [c[3] for c in cells])
    out = []
    for (x0, top, x1, bottom) in cells:
        c0, c1 = _idx(xs, x0), _idx(xs, x1)
        r0, r1 = _idx(ys, top), _idx(ys, bottom)
        if c1 <= c0 or r1 <= r0:
            continue
        crop = page.within_bbox((x0, top, x1, bottom), strict=False)
        text = (crop.extract_text(x_tolerance=3, y_tolerance=y_tol) or "").replace("\n", " ").strip()
        out.append({"r0": r0, "r1": r1, "c0": c0, "c1": c1, "bbox": (x0, top, x1, bottom), "text": text,
                    "bold": _is_bold(crop.chars)})
    return len(ys) - 1, len(xs) - 1, out


def header_rows(cells: list[dict], nrows: int) -> int:
    """表頭列數：從第一列開始，非空格全為粗體、或全是 MIN/TYP/MAX 類字詞的列。"""
    n = 0
    for r in range(nrows):
        row_cells = [c for c in cells if c["r0"] == r and c["text"]]
        if not row_cells:
            if n:
                n += 1
                continue
            break
        if all(c["bold"] for c in row_cells) or all(c["text"].lower() in _HEADER_WORDS for c in row_cells):
            n = max(n, max(c["r1"] for c in row_cells))
        else:
            break
    return n
