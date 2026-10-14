"""從 PDF 文字層列出所有 figure caption，寫入 golden 的 "figures"（保留既有 "parameters"）。

  .venv-docling\\Scripts\\python.exe scripts\\make_golden_figures.py <pdf> <golden.json> [--dry-run]

規則：一行以 "Figure N" / "Fig. N" 開頭（N 可帶字母，如 58a），且不是目錄行（結尾沒有 ..... 頁碼）。
用 pypdfium2 取文字，刻意不用 pdfplumber（pdfplumber 是受測方法之一）。產出後請人工檢查。
"""
import json
import re
import sys
from pathlib import Path

import pypdfium2 as pdfium

NUM = r"(\d+[a-z]?(?:-\d+[a-z]?)?)"
# 行首的 caption：Figure 3-1. Typical… / Figure 7 EZ-PD…（Infineon 沒有句點）
LINE_RE = re.compile(rf"^\s*fig(?:ure)?\.?\s*{NUM}\s*[.:\-–—]?\s*(.*)$", re.I)
# 行中的 caption：兩張圖並排時 caption 在同一行（Figure 1a. … Figure 1b. …）；要求「句點 + 大寫」
INLINE_RE = re.compile(rf"(?<!\w)figure\s*{NUM}\.\s+(?=[A-Z0-9])", re.I)
TOC_RE = re.compile(r"(\.{4,}|…{2,}|(\.\s){4,})\s*\d+\s*$")


def _is_reference(rest: str) -> bool:
    """Figure 26 allows… / Figure 2 shows… → 內文引用，不是 caption。"""
    w = rest.split()[0] if rest.split() else ""
    return bool(w) and w[0].islower()


REF_WORDS = {"in", "see", "to", "of", "and", "from", "on", "by", "at", "per", "as", "with", "the", "refer"}


def figure_captions(pdf_path: Path) -> list[dict]:
    pdf = pdfium.PdfDocument(str(pdf_path))
    out = []
    for i in range(len(pdf)):
        lines = [ln for ln in pdf[i].get_textpage().get_text_range().replace("\r", "").split("\n")
                 if not TOC_RE.search(ln)]
        # 第一輪：行首 caption（最可靠）；第二輪：行中並排的 caption（前一個字不是 in/see/to… 這類引用語）
        found: dict[str, str] = {}
        for line in lines:
            m = LINE_RE.match(line)
            if m and not _is_reference(m.group(2)):
                found.setdefault(m.group(1), line)
        for line in lines:
            for mm in INLINE_RE.finditer(line):
                prev = line[:mm.start()].split()
                if mm.start() == 0 or (prev and prev[-1].lower().strip("(,") in REF_WORDS):
                    continue
                found.setdefault(mm.group(1), line[mm.start():])
        for num, cap in found.items():
            nxt = INLINE_RE.search(cap, 1)
            cap = cap[:nxt.start()] if nxt else cap
            out.append({"page": i + 1, "label": f"Figure {num}", "caption": " ".join(cap.split())[:160]})
    pdf.close()
    return out


if __name__ == "__main__":
    pdf, golden = Path(sys.argv[1]), Path(sys.argv[2])
    figs = figure_captions(pdf)
    for f in figs:
        print(f"p{f['page']:<4} {f['caption']}")
    print(len(figs), "figures")
    if "--dry-run" not in sys.argv:
        data = json.loads(golden.read_text(encoding="utf-8")) if golden.exists() else {"datasheet": pdf.name, "parameters": []}
        data["figures"] = figs
        data["figures_source"] = "pypdfium2 text layer, 'Figure N' caption lines (scripts/make_golden_figures.py), reviewed"
        golden.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
