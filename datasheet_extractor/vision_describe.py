"""Granite Vision 3.3 2B 圖片描述（hybrid 後端用；每張圖帶自己的 prompt，Docling 內建描述做不到）。

權重：models/docling/ibm-granite--granite-vision-3.3-2b（scripts/download_models.py 下載，與 Docling 共用）。
"""
from __future__ import annotations

from pathlib import Path

from .model_env import DOCLING_MODELS

REPO_ID = "ibm-granite/granite-vision-3.3-2b"
LOCAL_DIR = DOCLING_MODELS / "ibm-granite--granite-vision-3.3-2b"


class GraniteVision:
    def __init__(self, path: Path | None = None, max_side: int = 1280):
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        path = path or LOCAL_DIR
        if not Path(path).exists():
            from huggingface_hub import snapshot_download   # 只在有網路時；DSX_OFFLINE=1 會直接報錯
            path = snapshot_download(REPO_ID)
        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.max_side = max_side
        self.processor = AutoProcessor.from_pretrained(path)
        self.model = AutoModelForImageTextToText.from_pretrained(
            path, dtype=torch.bfloat16 if self.device == "cuda" else torch.float32, device_map=self.device)
        self.model.eval()

    def describe(self, image, prompt: str, max_new_tokens: int = 400) -> str:
        if max(image.size) > self.max_side:   # anyres 切塊數隨尺寸增加；限制最長邊，避免 8 GB VRAM 不夠
            s = self.max_side / max(image.size)
            image = image.resize((max(1, int(image.width * s)), max(1, int(image.height * s))))
        conv = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": prompt}]}]
        text = self.processor.apply_chat_template(conv, add_generation_prompt=True)
        inputs = self.processor(text=[text], images=[image.convert("RGB")], return_tensors="pt").to(self.device)
        with self.torch.inference_mode():
            out = self.model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
        return self.processor.decode(out[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()

    def close(self) -> None:
        del self.model
        if self.device == "cuda":
            self.torch.cuda.empty_cache()
