"""Survey each PDF: page count, title lines, pages mentioning electrical-spec headings, figure caption count."""
import re
import sys
from pathlib import Path

import pypdfium2 as pdfium

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_golden_figures import figure_captions  # noqa: E402

KW = re.compile(r"(absolute maximum|electrical characteristics|dc characteristics|ac characteristics|"
                r"recommended operating|operating conditions|timing|switching characteristics)", re.I)
for pdf_path in sorted(Path(sys.argv[1]).glob("*.pdf")):
    pdf = pdfium.PdfDocument(str(pdf_path))
    first = pdf[0].get_textpage().get_text_range().strip().splitlines()[:6]
    hits = {}
    for i in range(len(pdf)):
        t = pdf[i].get_textpage().get_text_range()
        for line in t.splitlines():
            if KW.search(line) and len(line) < 90 and not re.search(r"\.{4,}", line):
                hits.setdefault(i + 1, []).append(line.strip())
    print(f"##### {pdf_path.name}: {len(pdf)} pages, figures {len(figure_captions(pdf_path))}")
    print("  first page:", " | ".join(first))
    for p, lines in hits.items():
        print(f"  p{p}: {' | '.join(dict.fromkeys(lines))[:220]}")
    pdf.close()
