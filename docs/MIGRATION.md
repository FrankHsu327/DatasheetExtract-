# 搬到內網機器

目標機器：Windows 11、RTX 4070 Laptop（8 GB）、可連 GitHub 與 PyPI、不能連 HuggingFace。

## 從 GitHub 取得（建議）

全部只需要 GitHub + PyPI：

```bash
git clone https://github.com/FrankHsu327/DatasheetExtract-.git datasheet-extractor
cd datasheet-extractor
powershell -ExecutionPolicy Bypass -File scripts\fetch_models.ps1
powershell -ExecutionPolicy Bypass -File scripts\setup_envs.ps1
```

- 程式碼在 repo；**模型權重**在 Release `models-v1`（`models-docling.zip.001`–`.004`，每個 < 2 GB，`SHA256SUMS.txt`）。
  `fetch_models.ps1` 下載、逐一驗 SHA-256、合併、再驗一次、解壓到 `models\docling\`。
  瀏覽器手動下載也可以：把檔案放在同一資料夾，執行 `fetch_models.ps1 -From <資料夾>`。
- **torch wheels 沒有上傳**：`wheels\` 不存在時，`setup_envs.ps1` 會從 download.pytorch.org 安裝 CUDA 12.6 版 torch。
  若公司機器連不到該網站，在這台機器執行 `scripts\pack_release.py --wheels` 後另外上傳 `wheels-torch-cu126.zip.*`，
  再用 `fetch_models.ps1 -Wheels`。
- Datasheet PDF 不在 repo，清單見 `DATASHEETS.txt`，自行下載放到 `datasheet\`。
- 重新打包權重：`.venv-docling\Scripts\python.exe scripts\pack_release.py`（輸出 `dist\github_release\`）。

## 帶什麼過去（離線複製，替代方案）

在這台機器執行 `scripts\make_bundle.ps1`，產出 `dist\datasheet-extractor\`，整個資料夾複製過去即可：

| 內容 | 大小 | 為什麼要帶 |
|---|---|---|
| 程式碼、config、prompts、golden、datasheet | 小 | — |
| `models\docling\` | 約 6.7 GB | Docling layout／TableFormer／圖片分類（0.7 GB）+ **Granite Vision 3.3 2B**（圖片描述，6.0 GB），全部在 HuggingFace |
| `wheels\` | 約 2.5 GB | torch / torchvision 的 CUDA 12.6 版只在 download.pytorch.org，不在 PyPI |
| `requirements\lock-docling.txt` | 小 | 這裡測過的確切版本 |
| `CHECKSUMS.sha256` | 小 | models 與 wheels 每個檔案的 SHA-256 |

不帶：`.venv-docling`（Windows venv 內含絕對路徑，換路徑就壞）、`tools\`（會從 GitHub 重新下載）、`out\`、`logs\`。

pdfplumber 沒有權重，安裝時從 PyPI 取得。三個元件的授權都可商用：pdfplumber（MIT）、Docling（MIT）、Granite Vision（Apache 2.0）。

## 在內網機器上

```bash
powershell -ExecutionPolicy Bypass -File scripts\setup_envs.ps1
```

1. 從 **GitHub** 下載 uv 0.13.0，再用 uv 從 **GitHub** 安裝獨立的 CPython 3.11（`tools\python\`）。
2. 建 `.venv-docling`；torch 從 `wheels\` 安裝，其餘依 lock 檔從 **PyPI** 安裝。
3. 結尾印出 `VERIFY ... cuda True`。

NVIDIA driver 需要 ≥ 561（CUDA 12.6）。`cuda False` 時先更新 driver。

離線複製時（GitHub 方式已由 `fetch_models.ps1` 驗證）：

```bash
.venv-docling\Scripts\python.exe scripts\checksums.py . verify
```

```bash
.venv-docling\Scripts\python.exe scripts\offline_check.py datasheet\0900766b81703faf.pdf 61-63
```

`offline_check.py` 會自己設定 `DSX_OFFLINE=1`。看到 `OFFLINE CHECK PASSED` 即完成。

## 模型位置與離線開關

由 `datasheet_extractor/model_env.py` 設定，全部在專案資料夾內：

```
models/docling/    Docling + Granite Vision（config: docling.artifacts_path）
models/hf/         HF_HOME（目前沒用到，保留）
```

`DSX_OFFLINE=1` 會設定 `HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`：任何一步想連 HuggingFace 都會直接報錯，不會默默下載。

## 已在這台機器驗證

搬移流程演練（`scripts\rehearse_migration.ps1`）：在 `dist\datasheet-extractor\`（全新複本，沒有 venv、沒有 tools）依上面步驟執行。

結果（2026-10-14）：
- uv 從 GitHub 下載、CPython 3.11 從 GitHub 安裝
- torch 從 `wheels\`、其餘依 lock 檔從 PyPI 安裝：`VERIFY docling 2.138.0 transformers 5.19.0 torch 2.14.1+cu126 cuda True`
- `CHECKSUMS OK`
- `DSX_OFFLINE=1` 下 docling 與 hybrid 都成功，hybrid 用 Granite Vision 描述了圖：`OFFLINE CHECK PASSED`
  （當時的 offline_check 還包含 docling 單獨方法；移除後只檢查 hybrid，需重新演練一次）
- bundle 大小 8.67 GB

`fetch_models.ps1 -From dist\github_release`（本機分割檔）在空資料夾還原：所有分割檔與合併後 zip 的 SHA-256 相符，
解出的 `models\docling` 每個檔案與 bundle 的 CHECKSUMS 一致（2026-10-14）。

從 GitHub Release `models-v1` 實際下載（`fetch_models.ps1`，空資料夾）：4 個分割檔 SHA-256 相符，
解出 44 個檔案與本機 `models\docling` 完全一致（2026-10-15）。

尚未驗證：在另一台機器上實際跑一次（只能在內網機器上做）。
