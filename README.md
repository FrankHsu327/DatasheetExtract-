# Datasheet Extractor

把元件 datasheet（PDF）轉成可驗證、可追溯的 component JSON，保留表格與圖片資訊。
Stage 1 是 hybrid：Docling 找表格與圖的位置、pdfplumber 從 PDF 文字層取表格內容、Granite Vision 描述圖；
之後是逐表抽取、覆蓋率追蹤、雙路比對與人工審核頁，用來解決「表格/圖表讀取會遺漏」的問題。

架構與盲點分析請看 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)；
為什麼選 hybrid（與 pdfplumber、Docling 單獨使用在 4 份 datasheet 上的比較，結果封存在 `out/compare/`；`out/` 不在 repo，比較結果與 hybrid 結果打包在 Release
[`compare-results-v1`](https://github.com/FrankHsu327/DatasheetExtract-/releases/tag/compare-results-v1)，在專案根目錄解壓後開 `out/compare/index.html`、`out/review/index.html`）請看 [`docs/METHOD_COMPARISON.md`](docs/METHOD_COMPARISON.md)；
搬到內網機器請看 [`docs/MIGRATION.md`](docs/MIGRATION.md)；待辦請看 [`docs/BACKLOG.md`](docs/BACKLOG.md)。

## 使用

```bash
powershell -ExecutionPolicy Bypass -File scripts\setup_envs.ps1       # 建 .venv-docling
powershell -ExecutionPolicy Bypass -File scripts\download_models.ps1  # 權重下載到 models/
powershell -ExecutionPolicy Bypass -File scripts\run_all.ps1          # datasheet\ 內全部 PDF → out\review\
```

產出：
- `out/review/index.html`：所有 datasheet 的分數彙總（有 golden 的才有分數）。
- `out/review/<stem>/compare.html`：左側是 hybrid 的輸出（逐頁；表格以 HTML 呈現；圖片顯示裁切圖、分類與描述），右側是原始 PDF 頁面。滑過左側項目會在右側框出位置，兩邊依頁同步捲動。
  - Parameters 分頁：點一列會跳到來源表格。
  - Summary 分頁：表格 fidelity、端到端 recall、圖片找到／描述數，以及逐參數對照。
- `out/review/<stem>/hybrid/<stem>.component.json`：最終產物。

全部在 `.venv-docling`；權重在 `models/docling`。hybrid 的設定在 `config/default.yaml` 的 `hybrid:`，圖片描述的 prompt 在 `prompts/figure_describe_hybrid.md`。

## 快速開始

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 1) 不需要 Docling 模型也能跑：用內建範例測試 Stage 2~4
python scripts/make_sample.py
python -m datasheet_extractor run-json samples/DS325Q32.docling.json \
       --pdf samples/DS325Q32.pdf --component spi_rom --out out/DS325Q32
python -m pytest -q

# 2) 真的 PDF（hybrid，需要 docling 與 models/）
python -m datasheet_extractor run datasheet/X.pdf --out out/
python -m datasheet_extractor run datasheet/ --out out/          # 整個資料夾
python -m datasheet_extractor view datasheet/X.pdf --golden golden/X.golden.json   # + 評分 + compare.html

# 3) 真實 datasheet 回歸測試（hybrid 表格部分，約 1–2 分鐘）
set DSX_SLOW=1
python -m pytest -q tests/test_real_datasheet.py
```

範例刻意模擬了 Docling 漏掉 AC 表中的 `tCLQX` 一列。跑完後，以下四個地方都會指出問題：
`expected missing: t_out_hold`、`crosscheck recall: T3=0.9091`、figure flag，以及 `evaluate` 的 `lost_in_docling`。

## 指令

| 指令 | 用途 |
|---|---|
| `run <pdf\|dir>` | 完整流程（Stage 1 hybrid + Stage 2–4） |
| `view <pdf> [--golden ...] [--reuse]` | 跑 hybrid、有 golden 就評分、產生 compare.html（`--reuse`：沿用 Stage 1，只重跑 Stage 2–4） |
| `summary [--out out/review]` | 所有 datasheet 的分數彙總 index.html |
| `run-json <document.json> --pdf <pdf> --out <dir>` | 從已轉好的 Docling JSON 跑 Stage 2–4，適合調規則、debug |
| `diagnose <document.json> [--pdf]` | 找可疑遺漏：表格被當成文字或圖、整張表沒被偵測到、空白過多的表 |
| `evaluate <component.json> <golden.json> [--docling-json]` | 與 golden set 比較，並歸因遺漏發生在哪一層 |

## 建議的工作順序

1. **先量化遺漏**：挑 3–5 份真實 datasheet 寫 golden set（見 `golden/README.md`），跑 `run` + `evaluate`。看 `loss_attribution` 決定先修哪一層：
   - `lost_in_docling` 多：調整 Stage 1，比較 `do_cell_matching` true/false，打開 `visualize_layout` 檢查。
   - `lost_in_extraction` 多：調整 `config/default.yaml` 的 `header_keywords`，或啟用 LLM。
   - `value_mismatch` 多：看 `review.html` 對照截圖，通常是註腳、單位或合併儲存格造成的。
2. **審核**：打開 `out/<stem>/review.html`，只需要看紅色（遺漏列）與黃色（有 flag）。
3. **串 LLM**（見下一節），再跑一次 golden set，確認 recall 有提升、沒有新增 `llm_value_not_in_source`。
4. **最後才處理圖**。

## 給 Devin 的串接清單

全部以 `TODO(Devin)` 標記，可以用 `grep -rn "TODO(Devin)" .` 找出來。

| # | 檔案 | 工作 | 完成後要改的 config |
|---|---|---|---|
| 1 | `datasheet_extractor/llm_client.py` | 實作 `CompanyLLMClient.complete()`（已附 OpenAI-compatible 範本）；憑證走環境變數 `COMPANY_LLM_URL / _TOKEN / _MODEL` | `llm.enabled: true` |
| 2 | `datasheet_extractor/vision_describe.py` | 選做：圖片描述改用公司視覺 LLM（同樣的 `describe(image, prompt)` 介面）；目前是本地 Granite Vision | — |
| 3 | — | 內網離線模型：已完成（`docling.artifacts_path: models/docling`，見 `docs/MIGRATION.md`） | — |
| 4 | `datasheet_extractor/stage3_extract.py` → `llm_extract()` | 大表依列分批，避免超過 context | — |
| 5 | `datasheet_extractor/crosscheck.py` | 選做：第三路比對，把 `tables/table_N.png` 送視覺 LLM 轉錄後逐格比對 | — |
| 6 | `datasheet_extractor/llm_client.py` | 把每次 request / response 記錄到 `out/<stem>/03_extract/llm_log/` | — |

串接時的驗收方式：
- `tests/test_llm_contract.py` 使用 `FakeLLMClient`，介面改動後仍須通過。
- 真實 LLM 串好後，以 golden set 跑 `evaluate`。recall 不得低於只用規則時的結果。

LLM 的 prompt 在 `prompts/table_extract.md`。若要修改，請保留以下約定：輸出純 JSON、每列 `row_id` 都必須出現、數值逐字複製。

## 目錄

```
config/            default.yaml、components/spi_rom.yaml
schemas/           component.schema.json
prompts/           table_extract.md、figure_describe.md、figure_describe_hybrid.md
datasheet_extractor/
  stage1_hybrid.py   Stage 1：Docling 找位置 + pdfplumber 取文字 + Granite Vision 描述圖
    docling_layout.py    Docling layout／TableFormer／圖片分類
    pdf_ruled_tables.py  pdfplumber 依框線重建表格
    vision_describe.py   Granite Vision 圖片描述
  stage2_tables.py  stage3_locate.py  stage3_extract.py  stage4_validate.py
  crosscheck.py  figures.py  llm_client.py  diagnose.py  evaluate.py  review.py  pipeline.py  cli.py
  view.py  compare_view.py  compare_template.html  summary.py   檢視器與分數彙總
  docling_reader.py  text_normalize.py  config.py  model_env.py
scripts/           setup_envs、download_models、run_all、make_bundle、offline_check、golden 工具
tests/             單元測試與端對端測試
golden/            golden set（人工標註）
docs/              ARCHITECTURE、METHOD_COMPARISON、MIGRATION、BACKLOG
out/compare/       方法比較結果（封存）
```

## 已知限制

- 端對端測試使用模擬的 Docling 輸出。在真實 PDF 上，`header_keywords`、`continuation_patterns` 這些規則需要依各廠牌排版微調。
- hybrid 的表格內容與 crosscheck 都依賴 PDF 文字層；掃描檔（沒有文字層）目前不支援，表格內容會是空的。
- 一份 PDF 涵蓋多個料號或多個電壓版本時，目前只會標出衝突，不會自動拆成多個 component。
- Typical characteristics 曲線不做數位化（刻意的設計決策）。
