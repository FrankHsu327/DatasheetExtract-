"""跑 hybrid（Stage 1–4）→ 有 golden 就評分 → 產生 compare.html（左：輸出，右：原始 PDF）。

Stage 1 在獨立 subprocess 執行（結束後 GPU 記憶體完整釋放；崩潰不影響主程式）。

out/review/<stem>/hybrid/   完整 pipeline 輸出 + run.json（狀態、耗時、錯誤）+ evaluate.json
out/review/<stem>/compare.html

方法比較時期（pdfplumber／Docling／hybrid）的結果封存在 out/compare/，本模組不會寫入那裡（預設輸出 out/review）。
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from .config import load_config

METHOD = "hybrid"
LABEL = "Hybrid (pdfplumber + Docling + Granite Vision)"

_STAGE1 = ("import sys; from pathlib import Path; "
           "from datasheet_extractor.model_env import setup; setup(); "
           "from datasheet_extractor.config import load_config; "
           "from datasheet_extractor.pipeline import run_stage1; "
           "run_stage1(Path(sys.argv[1]), Path(sys.argv[2]), load_config(sys.argv[3]))")


def _run(pdf: Path, mdir: Path, component: str, reuse_stage1: bool) -> dict:
    from .pipeline import run_from_docling_json

    mdir.mkdir(parents=True, exist_ok=True)
    info = {"id": METHOD, "label": LABEL, "status": "ok", "elapsed_sec": None, "error": None}
    dj = mdir / "01_docling" / "document.json"
    prev = mdir / "run.json"
    if reuse_stage1 and dj.exists() and prev.exists():
        info["elapsed_sec"] = json.loads(prev.read_text(encoding="utf-8")).get("elapsed_sec")
    else:
        t0 = time.time()
        log = mdir / "stage1.log"
        with open(log, "w", encoding="utf-8") as fh:
            proc = subprocess.run([sys.executable, "-c", _STAGE1, str(pdf), str(mdir), component],
                                  stdout=fh, stderr=subprocess.STDOUT, cwd=Path(__file__).resolve().parent.parent)
        info["elapsed_sec"] = round(time.time() - t0, 1)
        if proc.returncode != 0 or not dj.exists():
            info["status"] = "stage1 failed"
            info["error"] = log.read_text(encoding="utf-8", errors="replace")[-3000:]
            return info
    try:
        run_from_docling_json(dj, mdir, load_config(component), pdf_path=pdf, source_name=pdf.name)
    except Exception as ex:  # noqa: BLE001
        import traceback
        info["status"] = "stage2-4 failed"
        info["error"] = "".join(traceback.format_exception(ex))[-3000:]
    return info


def view(pdf: Path, out_root: Path, component: str = "generic", golden: str | None = None,
         reuse_stage1: bool = False) -> Path:
    stem_dir = out_root / pdf.stem
    mdir = stem_dir / METHOD
    print(f"[{METHOD}] {'stage 1 reused, running stage 2-4' if reuse_stage1 else 'running'} ...", flush=True)
    info = _run(pdf, mdir, component, reuse_stage1)
    (mdir / "run.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{METHOD}] {info['status']} (stage 1: {info['elapsed_sec']}s)", flush=True)

    gold = json.loads(Path(golden).read_text(encoding="utf-8")) if golden else None
    comp_files = list(mdir.glob("*.component.json"))
    dj = mdir / "01_docling" / "document.json"
    if gold and comp_files and dj.exists():
        from .docling_reader import DoclingDoc
        from .evaluate import evaluate
        ev = evaluate(json.loads(comp_files[0].read_text(encoding="utf-8")), gold, DoclingDoc.load(dj))
        (mdir / "evaluate.json").write_text(json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")
        fig = ev.get("figures") or {}
        print(f"[{METHOD}] stage1 fidelity {ev['stage1']['fidelity']}  end-to-end recall {ev['recall']}"
              f"  figures found {fig.get('recall')}  described {fig.get('described_ratio')}")

    from .compare_view import build
    return build(stem_dir, pdf, [info], gold)
