"""Experiment: can Granite Vision read a ball map by itself? (W25Q128JV Figure 1d, page 8)

Scores each variant against the true ball→signal map of Package Code B and C.
  .venv-docling\\Scripts\\python.exe scripts\\exp_ballmap.py datasheet\\0900766b81703faf.pdf
"""
import re
import sys
import time
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datasheet_extractor.model_env import setup  # noqa: E402

setup()
from datasheet_extractor.vision_describe import GraniteVision  # noqa: E402

PAGE, BOX = 8, (71, 142, 524, 381)      # Figure 1d region (top-left pt), from the hybrid output
SCALE = 3.0

ROW_B = {"A": ["", "NC", "NC", "/RESET", "NC"], "B": ["NC", "CLK", "GND", "VCC", "NC"],
         "C": ["NC", "/CS", "NC", "/WP(IO2)", "NC"], "D": ["NC", "DO(IO1)", "DI(IO0)", "/HOLD(IO3)", "NC"],
         "E": ["NC"] * 5}
ROW_C = {"A": ["NC", "NC", "NC", "/RESET"], "B": ["NC", "CLK", "GND", "VCC"], "C": ["NC", "/CS", "NC", "/WP(IO2)"],
         "D": ["NC", "DO(IO1)", "DI(IO0)", "/HOLD(IO3)"], "E": ["NC"] * 4, "F": ["NC"] * 4}
TRUTH = {
    "B": {f"{r}{i + 1}": s for r, row in ROW_B.items() for i, s in enumerate(row) if s},
    "C": {f"{r}{i + 1}": s for r, row in ROW_C.items() for i, s in enumerate(row)},
}

EXPLICIT = ("This image is a ball assignment figure from an electronic component datasheet. "
            "{scope}List every ball that is actually drawn, one per line, as BALL=SIGNAL (for example B2=CLK). "
            "Copy signal names exactly as printed. Do not list balls that are not drawn. No other text.")
HYBRID = (Path(__file__).resolve().parent.parent / "prompts" / "figure_describe_hybrid.md").read_text(encoding="utf-8")

PAIR = re.compile(r"\b([A-F])\s*([1-5])\s*[=:\-]\s*([/A-Za-z0-9() ]+?)(?=$|[,;\n]|\s+[A-F]\s*[1-5]\s*[=:\-])", re.M)


def norm(s: str) -> str:
    return re.sub(r"[\s_]", "", s).upper().replace("I/O", "IO")


def score(text: str, truth: dict) -> dict:
    got = {}
    for r, c, sig in PAIR.findall(text):
        got.setdefault(f"{r}{c}", norm(sig))
    ok = sum(1 for k, v in truth.items() if got.get(k) == norm(v))
    extra = sorted(k for k in got if k not in truth)
    wrong = sorted(k for k, v in truth.items() if k in got and got[k] != norm(v))
    missing = sorted(k for k in truth if k not in got)
    return {"correct": f"{ok}/{len(truth)}", "wrong": wrong, "missing": missing, "invented": extra}


def main(pdf_path: str) -> None:
    page_img = pdfium.PdfDocument(pdf_path)[PAGE - 1].render(scale=SCALE).to_pil()
    crop = lambda b: page_img.crop(tuple(int(v * SCALE) for v in b))   # noqa: E731
    mid = (BOX[0] + BOX[2]) / 2
    whole, left, right = crop(BOX), crop((BOX[0], BOX[1], mid, BOX[3])), crop((mid, BOX[1], BOX[2], BOX[3]))
    with pdfplumber.open(pdf_path) as pdf:
        flat = " ".join((pdf.pages[PAGE - 1].crop(BOX).extract_text(x_tolerance=2) or "").split())

    vlm = GraniteVision(max_side=1600)
    runs = [
        ("V1 whole, no text, hybrid prompt", whole,
         HYBRID.replace("{{CAPTION}}", "Figure 1d. W25Q128JV Ball Assignments, 24-ball TFBGA 8x6-mm (Package Code B/C)")
               .replace("{{PDF_TEXT}}", "(none)"), None),
        ("V2 whole, no text, explicit", whole,
         EXPLICIT.format(scope="It shows two packages, Package Code B (left) and Package Code C (right). "
                               "Write 'Package Code B:' then its balls, then 'Package Code C:' then its balls. "), None),
        ("V3 split crops, no text, explicit", None, None, None),
        ("V4 whole, flattened text, explicit", whole,
         EXPLICIT.format(scope="It shows two packages, Package Code B (left) and Package Code C (right). "
                               "Write 'Package Code B:' then its balls, then 'Package Code C:' then its balls. ")
         + f"\nText from the PDF inside the figure: {flat}", None),
    ]
    for name, img, prompt, _ in runs:
        t0 = time.time()
        if name.startswith("V3"):
            out_b = vlm.describe(left, EXPLICIT.format(scope=""), 500)
            out_c = vlm.describe(right, EXPLICIT.format(scope=""), 500)
            parts = {"B": out_b, "C": out_c}
            raw = f"[B]\n{out_b}\n[C]\n{out_c}"
        else:
            raw = vlm.describe(img, prompt, 600)
            m = re.split(r"package\s*code\s*c", raw, flags=re.I)
            parts = {"B": m[0], "C": m[1] if len(m) > 1 else ""}
        print(f"\n######## {name}  ({time.time() - t0:.1f}s)")
        print(raw[:1500])
        for pkg in ("B", "C"):
            print(f"  score {pkg}:", score(parts[pkg], TRUTH[pkg]))


if __name__ == "__main__":
    main(sys.argv[1])
