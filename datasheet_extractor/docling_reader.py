"""Read an exported DoclingDocument JSON (doc.export_to_dict()) without importing docling.

Stage 2+ 只依賴這份 JSON，因此可以在沒有 docling/torch 的環境（或 CI）執行與測試。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

BBox = tuple[float, float, float, float]  # (l, t, r, b) in TOP-LEFT origin, PDF points


class DoclingDoc:
    def __init__(self, data: dict[str, Any]):
        self.data = data

    @classmethod
    def load(cls, path: str | Path) -> "DoclingDoc":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    # ------------------------------------------------------------------ refs
    def resolve(self, ref: str | dict | None) -> dict | None:
        if ref is None:
            return None
        if isinstance(ref, dict):
            ref = ref.get("$ref") or ref.get("cref")
        if not ref or not ref.startswith("#/"):
            return None
        parts = ref[2:].split("/")
        node: Any = self.data
        for p in parts:
            node = node[int(p)] if isinstance(node, list) else node[p]
        return node

    def iter_body(self) -> Iterator[dict]:
        """Depth-first walk of the body tree = reading order. Yields doc items (texts/tables/pictures)."""
        def walk(node: dict):
            for child in node.get("children", []):
                item = self.resolve(child)
                if item is None:
                    continue
                ref = item.get("self_ref", "")
                if ref.startswith(("#/texts", "#/tables", "#/pictures")):
                    yield item
                if item.get("children") and not ref.startswith(("#/tables", "#/pictures")):
                    yield from walk(item)
        yield from walk(self.data.get("body", {}))

    # ------------------------------------------------------------ geometry
    def page_size(self, page_no: int) -> tuple[float, float]:
        page = self.data.get("pages", {}).get(str(page_no)) or {}
        size = page.get("size") or {}
        return float(size.get("width", 612.0)), float(size.get("height", 792.0))

    def bbox_topleft(self, prov: dict) -> BBox:
        bb = prov["bbox"]
        l, t, r, b = float(bb["l"]), float(bb["t"]), float(bb["r"]), float(bb["b"])
        origin = str(bb.get("coord_origin", "BOTTOMLEFT")).upper()
        if "BOTTOM" in origin:
            _, h = self.page_size(int(prov["page_no"]))
            t, b = h - t, h - b
        if t > b:
            t, b = b, t
        return (l, t, r, b)

    def provenance(self, item: dict) -> list[dict]:
        out = []
        for p in item.get("prov", []) or []:
            out.append({"page": int(p["page_no"]), "bbox": [round(v, 2) for v in self.bbox_topleft(p)],
                        "ref": item.get("self_ref")})
        return out

    def child_texts(self, item: dict) -> list[str]:
        """Text items nested under a picture (Docling 會把圖內可擷取的文字掛在 picture 底下)."""
        out = []
        stack = list(item.get("children", []) or [])
        while stack:
            node = self.resolve(stack.pop(0))
            if not node:
                continue
            if node.get("text"):
                out.append(node["text"])
            stack.extend(node.get("children", []) or [])
        return out

    # ----------------------------------------------------------- captions
    def caption_text(self, item: dict) -> str:
        texts = []
        for c in item.get("captions", []) or []:
            t = self.resolve(c)
            if t and t.get("text"):
                texts.append(t["text"])
        return " ".join(texts).strip()

    def footnote_texts(self, item: dict) -> list[str]:
        out = []
        for c in item.get("footnotes", []) or []:
            t = self.resolve(c)
            if t and t.get("text"):
                out.append(t["text"])
        return out

    @property
    def name(self) -> str:
        return self.data.get("name", "document")

    @property
    def origin_hash(self) -> str | None:
        return (self.data.get("origin") or {}).get("binary_hash")


def table_grid(table: dict) -> tuple[list[list[str]], list[list[dict]]]:
    """Build a dense grid from table_cells honouring row/col spans.

    Spanned cells are copied into every covered position (same as docling's TableData.grid);
    each position also gets meta: column_header / row_header / row_section / spanned / origin(row,col).
    """
    data = table.get("data") or {}
    nrows, ncols = int(data.get("num_rows", 0)), int(data.get("num_cols", 0))
    cells = data.get("table_cells") or []
    if not nrows or not ncols:
        for c in cells:
            nrows = max(nrows, int(c["end_row_offset_idx"]))
            ncols = max(ncols, int(c["end_col_offset_idx"]))
    grid = [["" for _ in range(ncols)] for _ in range(nrows)]
    meta = [[{"column_header": False, "row_header": False, "row_section": False, "spanned": False,
              "origin": (r, c)} for c in range(ncols)] for r in range(nrows)]
    for cell in cells:
        r0, r1 = int(cell["start_row_offset_idx"]), int(cell["end_row_offset_idx"])
        c0, c1 = int(cell["start_col_offset_idx"]), int(cell["end_col_offset_idx"])
        for r in range(r0, min(r1, nrows)):
            for c in range(c0, min(c1, ncols)):
                grid[r][c] = cell.get("text", "") or ""
                meta[r][c] = {
                    "column_header": bool(cell.get("column_header")),
                    "row_header": bool(cell.get("row_header")),
                    "row_section": bool(cell.get("row_section")),
                    "spanned": (r, c) != (r0, c0),
                    "origin": (r0, c0),
                }
    return grid, meta
