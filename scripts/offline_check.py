"""離線驗證：DSX_OFFLINE=1（HF_HUB_OFFLINE=1）下，hybrid 的所有模型都能從 models/ 載入。

  .venv-docling\\Scripts\\python.exe scripts\\offline_check.py <pdf> [pages, 預設 61-63]

只取幾頁做成小 PDF，重跑 hybrid 的 Stage 1（Docling layout／TableFormer／圖片分類 + pdfplumber + Granite Vision），
並檢查至少描述了一張圖。搬到內網機器後先跑這支，確認權重完整、沒有任何一步需要連 HuggingFace。
"""
import json
import os
import sys
from pathlib import Path

os.environ["DSX_OFFLINE"] = "1"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pypdfium2 as pdfium  # noqa: E402

from datasheet_extractor.model_env import setup  # noqa: E402
from datasheet_extractor.view import view  # noqa: E402

print(setup())
src = Path(sys.argv[1])
first, last = (int(x) for x in (sys.argv[2] if len(sys.argv) > 2 else "61-63").split("-"))
out = ROOT / "out" / "offline_check"
out.mkdir(parents=True, exist_ok=True)
sub = out / f"{src.stem}_p{first}-{last}.pdf"
doc, new = pdfium.PdfDocument(str(src)), pdfium.PdfDocument.new()
new.import_pages(doc, list(range(first - 1, last)))
new.save(str(sub))

view(sub, out)   # 沒有 --reuse：Stage 1 一律重跑
mdir = out / sub.stem / "hybrid"
info = json.loads((mdir / "run.json").read_text(encoding="utf-8"))
print(f"hybrid  {info['status']}  {info['elapsed_sec']}s")
bad = []
if info["status"] != "ok":
    bad.append("hybrid")
    print(info["error"])
else:
    meta = json.loads((mdir / "01_docling" / "meta.json").read_text(encoding="utf-8"))
    fig = (meta.get("hybrid") or {}).get("figures") or {}
    print("hybrid figures:", fig, " tables:", (meta.get("hybrid") or {}).get("table_sources"))
    if not fig.get("described"):
        bad.append("hybrid (no figure described: Granite Vision did not run)")
print("OFFLINE CHECK", "FAILED: " + ", ".join(bad) if bad else "PASSED")
