# Stage 1 方法比較（4 份 datasheet、3 種方法）

目的：選出把 datasheet PDF 轉成 JSON（表格 + 圖）最好的方法。這是通用 datasheet 抽取器，不針對特定元件；
特定元件的參數判讀交給另一個專案的 LLM。

逐頁對照：`out/compare/index.html`（彙總）→ 點各 datasheet 進入 `compare.html`（左：方法輸出，右：原始 PDF）。

## 範圍與已排除的方案

| 方案 | 狀態 | 原因 |
|---|---|---|
| pdfplumber | 保留 | MIT；不需模型 |
| Docling + Granite Vision | 保留（對照組） | MIT / Apache 2.0；權重 6.7 GB |
| **hybrid**（pdfplumber + Docling + Granite Vision） | **建議** | 同上；見下 |
| MinerU | 已移除 | 公司不允許使用 |
| granite-docling-258M | 已移除 | 表格 fidelity 平均 43%、每頁約 15 秒 |
| Chandra / Marker（Datalab） | 未採用 | 權重授權（modified OpenRAIL-M）限制商用：營收／募資超過 200 萬（Chandra）或 500 萬美元（Marker）需付費授權；Chandra 5B BF16 約需 10 GB VRAM，8 GB GPU 放不下；Marker 在 NVIDIA GPU 上需 Docker + vLLM |

## 測試資料

| Datasheet | 元件 | 頁數 | 規格表樣式 | Golden 參數 | Golden 圖 |
|---|---|---|---|---|---|
| W25Q128JV（`0900766b81703faf.pdf`） | Winbond SPI flash | 78 | 全框線 | 59 | 52 |
| RT3624LE（`DS3624LE-00.pdf`） | Richtek 雙通道 PWM 控制器 | 48 | 全框線、多層合併儲存格 | 28 | 26 |
| CCG6（`infineon-…-ccg6-…pdf`） | Infineon USB-C PD 控制器 | 61 | **只有橫線** | 27 | 24 |
| MC9S08SC4 | NXP 8-bit MCU | 31 | 全框線、子列縮排 | 23 | 10 |

- Golden 參數：從**頁面渲染圖**手抄（不看任何工具的輸出），檔案在 `golden/`。
- Golden 圖：PDF 文字層中所有 "Figure N" caption（`scripts/make_golden_figures.py`，pypdfium2），已人工檢查排除內文引用。

## hybrid 的做法

| 工作 | 誰負責 | 依據（上一輪比較） |
|---|---|---|
| 找表格、圖的位置 | Docling layout 模型 | 圖找到 99%；無框線表格也偵測得到 |
| 表格內容（有框線） | pdfplumber 在 Docling 的表格範圍內依框線重建 | pdfplumber 讀表 95%，Docling 60% |
| 表格內容（無框線） | Docling 的列／欄位置當格線，每格文字用 pdfplumber 的字 | 去掉 Docling 的錯字、空白格，保留它對無框線表的結構判斷 |
| 雙路比對 | 兩邊數字 token 差異 > 10% → `meta.json` 記 flag | Docling 讀錯的表會被標出來 |
| 漏掉的表 | 頁面上有框線、Docling 沒偵測到 → pdfplumber 補上 | 本輪 4 份都沒有發生 |
| 圖片描述 | Granite Vision 3.3 2B，datasheet 專用 prompt，帶入 caption 與 pdfplumber 從圖內讀到的文字 | Docling 預設 prompt 的描述幾乎都是「a circuit diagram of a digital logic circuit」 |

設定在 `config/default.yaml` 的 `hybrid:`，prompt 在 `prompts/figure_describe_hybrid.md`。

## 結果

| 方法 | 表格 fidelity（平均） | 端到端 recall（平均） | 圖找到 | 圖有描述 | 秒／頁 |
|---|---|---|---|---|---|
| pdfplumber | 95% | 90% | 95%* | 0% | **0.1** |
| Docling + Granite Vision | 60% | 2% | 99% | 90% | 3.3 |
| **hybrid** | **97%** | **90%** | **99%** | **94%** | 9.0 |

\* pdfplumber 的「找到」是依 caption 文字推估範圍，不是真的偵測圖。

| Datasheet | pdfplumber | Docling | hybrid |
|---|---|---|---|
| W25Q128JV | 100% | 83% | **100%** |
| RT3624LE | 93% | 75% | 93% |
| CCG6（只有橫線） | 93% | 48% | **100%** |
| MC9S08SC4 | 96% | 35% | 96% |

（表格 fidelity：golden 的 symbol 與所有數值出現在同一張表的同一列；不依賴 Stage 2–4 規則。）

- **端到端 recall**：Stage 2–4 規則抽出且數值正確。hybrid 與 pdfplumber 相同（90%），Docling 只有 2%。
- **秒／頁**：RTX 4060 Laptop 8 GB，含模型載入；RTX 4070 Laptop 預期相近。

### 時間花在哪（W25Q128JV，78 頁）

| 步驟 | 秒 |
|---|---|
| Docling（layout、TableFormer、圖片分類） | 45 |
| 表格重建（pdfplumber） | 8.5 |
| 圖片描述（Granite Vision，69 張，約 11 秒／張） | 764 |

表格部分約 0.7 秒／頁；慢的是圖片描述。不需要描述時設 `hybrid.describe: false`。

## 觀察

**表格：hybrid 在 4 份上都 ≥ pdfplumber。**
- W25Q128JV：39 張表中 34 張依框線重建、5 張用 Docling 格線；fidelity 100%。
- CCG6（只有橫線）：hybrid 100%，pdfplumber 93%、Docling 48%。Docling 的格線 + pdfplumber 的字補上了兩者各自的缺點。
- RT3624LE、MC9S08SC4 與 pdfplumber 相同：這兩份的表都有框線，hybrid 走的就是 pdfplumber 依框線重建，所以錯在同樣的地方（例如 RT3624LE 的多行儲存格）。

**圖片描述：比 Docling 預設好很多，但仍不可當作規格來源。**
- 會用正確名稱：pin／ball 圖列出腳位、暫存器圖列出 SRP / SEC / TB / BP2、power-up 圖點出 tPUW / tVSL / VWI。
- 曲線圖會講軸與條件（IOL mA、VOL V、125 / 25 / −40 °C），不讀數值。
- 仍會自行展開縮寫（把 VDD − VOH 說成 drain-to-source voltage、FEI 說成 Field Effect Injection），2B 模型不完全遵守 prompt 的規則。
- 描述中有數值 + 單位的圖會標 `numbers_in_description` + `needs_review`。
- 頁首／頁尾的 logo 條、icon 不描述（Winbond 頁首色條會被分類成 bar_chart，已排除）。

## 建議

1. **採用 hybrid。** 表格最好（97%），圖片找到 99%，描述可作為下游 LLM 的索引／檢索線索。
2. **不需要圖片描述時**（只要表格）：`hybrid.describe: false`，約 1 秒／頁。
3. **pdfplumber 作為 hybrid 的一部分**保留；`crosscheck` 也用它比對數字 token。
4. **Granite Vision 描述的可信度**：適合「這張圖在講什麼、有哪些訊號」，不適合當作數值或縮寫定義的依據。

## 結論後的處置（封存）

- 已決定 hybrid 為最終方案。pdfplumber、Docling 單獨使用的程式與多方法比較指令已從專案移除；
  hybrid 需要的部分保留為 `datasheet_extractor/docling_layout.py`（Docling layout）與 `pdf_ruled_tables.py`（pdfplumber 依框線重建）。
- 本文件的結果封存在 `out\compare\`（`index.html` 與各 datasheet 的 `compare.html` 都是自足的靜態頁，可直接開啟）。
- 之後的 hybrid 結果：`scripts\run_all.ps1` → `out\review\`（不會覆寫封存）。
