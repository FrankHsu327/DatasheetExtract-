"""Render selected PDF pages to PNG (for hand-transcribing golden sets from the page image).

  python scripts/render_pages.py <pdf> <out_dir> 8,9,10 [scale]
"""
import sys
from pathlib import Path

import pypdfium2 as pdfium

pdf, out = pdfium.PdfDocument(sys.argv[1]), Path(sys.argv[2])
scale = float(sys.argv[4]) if len(sys.argv) > 4 else 2.0
out.mkdir(parents=True, exist_ok=True)
for p in (int(x) for x in sys.argv[3].split(",")):
    pdf[p - 1].render(scale=scale).to_pil().save(out / f"p{p}.png")
    print(out / f"p{p}.png")
