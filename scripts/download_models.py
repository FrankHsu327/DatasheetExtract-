"""預先下載所有模型權重到 models/docling，供內網離線使用。

在可連 HuggingFace 的機器上執行：
  .venv-docling\\Scripts\\python.exe scripts\\download_models.py

下載內容（Docling 的 model_downloader，全部放在 docling.artifacts_path = models/docling）：
  layout（heron）、TableFormer、圖片分類器、Granite Vision 3.3 2B（圖片描述）
內網機器上：set DSX_OFFLINE=1 後，所有模型只從 models/ 讀取。
完成後重寫 models/manifest.json（資料夾、檔案數、大小），搬移後可比對。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from datasheet_extractor.model_env import DOCLING_MODELS, MODELS, setup  # noqa: E402

setup()


def _size(path: Path) -> tuple[int, int]:
    files = [p for p in path.rglob("*") if p.is_file()]
    return len(files), sum(p.stat().st_size for p in files)


def main() -> None:
    from docling.utils.model_downloader import download_models
    download_models(output_dir=DOCLING_MODELS, progress=True, with_layout=True, with_tableformer=True,
                    with_code_formula=False, with_picture_classifier=True, with_granite_vision=True,
                    with_rapidocr=False, with_easyocr=False)
    manifest = {}
    for d in sorted(p for p in DOCLING_MODELS.iterdir() if p.is_dir()):
        n, size = _size(d)
        manifest[d.name] = {"path": str(d.relative_to(ROOT)), "files": n, "bytes": size}
        print(f"  {d.name}: {n} files, {size / 1e6:.0f} MB")
    (MODELS / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
    print("DOWNLOAD DONE")
