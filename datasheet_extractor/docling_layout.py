"""hybrid 的第一步：Docling 標準流程（layout + TableFormer + 圖片分類），找出表格與圖的位置。

已驗證對應 docling 2.138 的 API：
  PdfPipelineOptions.table_structure_options = TableStructureOptions(mode=..., do_cell_matching=...)
  generate_table_images 已 deprecated → 改用 generate_page_images + TableItem.get_image(doc)

圖片描述不在這裡做：hybrid 用 Granite Vision + datasheet 專用 prompt 另外描述（vision_describe.py）。

輸出到 <out>/01_docling/：
  document.json   DoclingDocument（hybrid 之後會改寫表格內容與圖片描述）→ Stage 2+ 的唯一輸入
  document.md     人工快速瀏覽用
  pages/ tables/ figures/   頁面圖、表格截圖、圖片截圖
  meta.json       來源檔 hash、docling 版本、使用的 pipeline options
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_of(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_converter(cfg: dict):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode, TableStructureOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    from .model_env import ROOT

    d = cfg["docling"]
    opts = PdfPipelineOptions()
    opts.do_ocr = bool(d.get("do_ocr", False))
    opts.do_table_structure = True
    opts.table_structure_options = TableStructureOptions(
        mode=TableFormerMode.ACCURATE if d.get("table_mode", "accurate") == "accurate" else TableFormerMode.FAST,
        do_cell_matching=bool(d.get("do_cell_matching", False)),
    )
    opts.images_scale = float(d.get("images_scale", 2.0))
    opts.generate_page_images = bool(d.get("generate_page_images", True))
    opts.generate_picture_images = bool(d.get("generate_picture_images", True))
    opts.do_picture_classification = bool(d.get("do_picture_classification", True))
    opts.do_picture_description = False
    if d.get("artifacts_path"):
        ap = Path(d["artifacts_path"])
        ap = ap if ap.is_absolute() else ROOT / ap
        if ap.exists():
            opts.artifacts_path = str(ap)   # 內網離線模型路徑

    if d.get("visualize_layout") or d.get("visualize_tables"):
        from docling.datamodel.settings import settings
        settings.debug.visualize_layout = bool(d.get("visualize_layout"))
        settings.debug.visualize_tables = bool(d.get("visualize_tables"))
        # 輸出位置：settings.debug.debug_output_path（預設 ./debug）

    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}), opts


def save_result(result, source: Path, out: Path, opts, elapsed: float, backend: str) -> Path:
    """Write document.json / .md / images / meta.json for a docling ConversionResult."""
    for sub in ("pages", "tables", "figures"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    doc = result.document

    (out / "document.json").write_text(json.dumps(doc.export_to_dict(), ensure_ascii=False), encoding="utf-8")
    (out / "document.md").write_text(doc.export_to_markdown(), encoding="utf-8")

    saved = {"pages": 0, "tables": 0, "figures": 0}
    for page_no, page in (doc.pages or {}).items():
        if page.image and page.image.pil_image is not None:
            page.image.pil_image.save(out / "pages" / f"page_{page_no}.png")
            saved["pages"] += 1
    for i, table in enumerate(doc.tables):
        try:
            img = table.get_image(doc)
            if img is not None:
                img.save(out / "tables" / f"table_{i}.png")
                saved["tables"] += 1
        except Exception:  # noqa: BLE001
            pass
    for i, pic in enumerate(doc.pictures):
        try:
            img = pic.get_image(doc)
            if img is not None:
                img.save(out / "figures" / f"figure_{i}.png")
                saved["figures"] += 1
        except Exception:  # noqa: BLE001
            pass

    meta: dict[str, Any] = {
        "source_file": source.name,
        "source_sha256": sha256_of(source),
        "backend": backend,
        "status": str(result.status),
        "elapsed_sec": round(elapsed, 2),
        "docling_version": _pkg_version("docling"),
        "docling_core_version": _pkg_version("docling-core"),
        "pipeline_options": json.loads(opts.model_dump_json()) if hasattr(opts, "model_dump_json") else None,
        "saved_images": saved,
        "errors": [str(e) for e in (getattr(result, "errors", None) or [])],
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return out / "document.json"


def _pkg_version(name: str) -> str | None:
    try:
        from importlib.metadata import version
        return version(name)
    except Exception:  # noqa: BLE001
        return None
