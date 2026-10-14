"""模型權重位置：一律放在專案的 models/，整個資料夾可直接搬到內網機器。

  models/docling/   Docling layout / TableFormer / 圖片分類 + Granite Vision 3.3 2B（docling.artifacts_path）
  models/hf/        HF_HOME（保留；目前沒有模型放這裡）

  有網路（下載）：  不設 DSX_OFFLINE
  內網（離線）：    set DSX_OFFLINE=1  → HF_HUB_OFFLINE=1，任何一步想連 HuggingFace 都會直接報錯

必須在 import docling / transformers 之前呼叫 setup()。
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
DOCLING_MODELS = MODELS / "docling"
HF_HOME = MODELS / "hf"


def setup() -> dict:
    HF_HOME.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(HF_HOME)
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    offline = os.environ.get("DSX_OFFLINE") == "1"
    if offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
    return {"HF_HOME": str(HF_HOME), "offline": offline}
