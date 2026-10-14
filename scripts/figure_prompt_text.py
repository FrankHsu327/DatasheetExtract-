"""Reproduce the PDF text the hybrid fed into the Granite Vision prompt for pictures on one page."""
import sys
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datasheet_extractor.docling_reader import DoclingDoc  # noqa: E402

doc = DoclingDoc.load(sys.argv[1])
pdf_path, page_no = sys.argv[2], int(sys.argv[3])
with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[page_no - 1]
    for p in doc.data["pictures"]:
        pv = doc.provenance(p)
        if not pv or pv[0]["page"] != page_no:
            continue
        box = tuple(pv[0]["bbox"])
        W, H = float(page.width), float(page.height)
        box = (max(0, box[0]), max(0, box[1]), min(W, box[2]), min(H, box[3]))
        print("=== picture", p["self_ref"], "bbox", [round(v) for v in box], "caption:", doc.caption_text(p)[:60])
        print("--- as fed to the prompt (whitespace collapsed):")
        print(" ".join((page.crop(box, strict=False).extract_text(x_tolerance=2) or "").split())[:1200])
        print("--- same text with line breaks:")
        print(page.crop(box, strict=False).extract_text(x_tolerance=2))
