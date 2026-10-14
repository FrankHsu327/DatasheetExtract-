"""真實 datasheet 回歸測試（hybrid Stage 1 + Stage 2–4；需要 GPU／模型，約 1–2 分鐘）。

W25Q128JV（Winbond, Rev G, 2019-04-08）：公開可下載。
golden/W25Q128JV.golden.json 是依 pdftotext 原文獨立手抄 9.1~9.6 的 59 個參數。

執行：set DSX_SLOW=1 後跑 pytest；PDF 放在 samples/real/W25Q128JV.pdf 或 datasheet/0900766b81703faf.pdf。
圖片描述（Granite Vision）在這個測試關閉，只驗證表格。
"""
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PDF = next((p for p in (ROOT / "samples" / "real" / "W25Q128JV.pdf", ROOT / "datasheet" / "0900766b81703faf.pdf")
            if p.exists()), None)


@pytest.mark.skipif(PDF is None or os.environ.get("DSX_SLOW") != "1",
                    reason="set DSX_SLOW=1 and provide the W25Q128JV PDF to run")
def test_w25q128jv_hybrid(cfg, tmp_path):
    from datasheet_extractor.evaluate import evaluate_files
    from datasheet_extractor.model_env import setup
    from datasheet_extractor.pipeline import run

    setup()
    cfg["hybrid"]["describe"] = False
    comp = run(PDF, tmp_path, cfg)
    q = comp["quality"]
    assert q["expected_parameters"]["missing"] == []
    spec = [c for c in q["coverage"] if c["category"] in ("absolute_max", "recommended_operating", "power_up",
                                                         "dc_characteristics", "ac_characteristics")]
    assert spec and all(c["coverage"] == 1.0 for c in spec)
    ac = next(t for t in comp["tables"] if t["category"] == "ac_characteristics")
    assert len(ac["source_refs"]) == 2, "AC 表跨頁（Continued – next page）應合併"
    tclqx = next(p for p in comp["parameters"] if p["symbol"] == "tCLQX")
    assert tclqx["alt_symbol"] == "tHO"
    out = tmp_path / PDF.stem
    res = evaluate_files(out / f"{PDF.stem}.component.json", ROOT / "golden" / "W25Q128JV.golden.json",
                         out / "01_docling" / "document.json")
    assert res["recall"] == 1.0, res["status_count"]
