"""Copy a page range of a PDF into a new PDF (quick timing / debugging runs).

  python scripts/make_subset.py <pdf> <first-last> <out.pdf>
"""
import sys
from pathlib import Path

import pypdfium2 as pdfium

src, rng, dst = sys.argv[1], sys.argv[2], sys.argv[3]
Path(dst).parent.mkdir(parents=True, exist_ok=True)
first, last = (int(x) for x in rng.split("-"))
doc, new = pdfium.PdfDocument(src), pdfium.PdfDocument.new()
new.import_pages(doc, list(range(first - 1, last)))
new.save(dst)
print(dst, last - first + 1, "pages")
