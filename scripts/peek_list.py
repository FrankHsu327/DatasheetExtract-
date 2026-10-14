"""Show Docling items around a text (label, marker, enumerated, x position, parent) + pdfplumber font/x of that line."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datasheet_extractor.docling_reader import DoclingDoc  # noqa: E402

doc = DoclingDoc.load(sys.argv[1])
needle = sys.argv[2]
texts = doc.data["texts"]
idx = next(i for i, t in enumerate(texts) if needle in (t.get("text") or ""))
for t in texts[max(0, idx - 2): idx + 7]:
    pv = doc.provenance(t)
    print(json.dumps({"label": t.get("label"), "marker": t.get("marker"), "enumerated": t.get("enumerated"),
                      "parent": (t.get("parent") or {}).get("$ref"), "x0": pv[0]["bbox"][0] if pv else None,
                      "text": t.get("text")[:60], "first_char": hex(ord(t["text"][0])) if t.get("text") else None},
                     ensure_ascii=False))
if len(sys.argv) > 3:
    import pdfplumber
    with pdfplumber.open(sys.argv[3]) as pdf:
        page = pdf.pages[int(sys.argv[4]) - 1]
        for ln in page.extract_text_lines(return_chars=True):
            if any(k in ln["text"] for k in ("SpiFlash", "128M-bit", "Standard SPI", "Dual SPI", "Quad SPI", "Software")):
                c = ln["chars"]
                print(f"x0={ln['x0']:.1f} font={c[0]['fontname']} / {c[min(3, len(c)-1)]['fontname']} first={hex(ord(c[0]['text']))} | {ln['text'][:60]}")
