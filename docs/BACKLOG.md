# 待辦（已確認、尚未實作）

## 1. 清單階層（巢狀 bullet）

現象：W25Q128JV「2. FEATURES」的子項目（– W25Q128JV: 128M-bit…）與父項目（• New Family of SpiFlash Memories）
被 Docling 放在同一層 list；父項目開頭的 • 顯示成 □。

原因（`document.json` 已有的資訊）：
- 父項目：marker 空白、x0 ≈ 81 pt、第一個字元 U+F0B7（Symbol 字型的 • 放在私有區）
- 子項目：marker "-"、x0 ≈ 90 pt
- 全部掛在同一個 `#/groups/N`

做法：
1. U+F0B7、U+F0A7、U+F06C 等私有區 bullet → "•"，當成 marker，不留在文字裡。
2. 同一個 list 內依 x0 縮排重建巢狀（縮排較深 → 上一個較淺項目的子 list；marker 不同為輔助判斷），寫回 DoclingDocument 的 list group 結構。
3. compare 檢視器顯示縮排；四份 datasheet 的 list 都檢查一次。

預估：半天。

## 2. Pin map／ball map 被當成表格 → 改成圖

現象：W25Q128JV Figure 1a–1e 的腳位圖（Top View、腳位編號、訊號名稱）被 Docling 判成表格；hybrid 再把封裝外框線當表格框線，產出雜亂的「表格」。
Stage 3 因沒有 MIN/MAX 欄不會抽，但輸出裡多了垃圾表，且圖片評分漏算這些圖。

決定：當成圖（不抽成表格）。腳位資料以 Pin Description 表格為準（W25Q128JV 3.3／3.5／3.7／3.9，hybrid 已能正確讀取）。

做法（hybrid Stage 1，Docling 跑完後、表格重建前）：
1. 判斷：對每張 Docling 表格
   - Figure caption：caption 或表格下方約 30 pt 內第一行以 "Figure" 開頭（真表格是 "Table N"）
   - 視圖字樣：範圍內有 "Top View" / "Bottom View" / "Package Code"
   - 腳位樣式：多數非空格 ≤ 2 個 token，且大量為 1…N 或 A1–H8 這類腳位編號
   - 沒有規格表頭：表頭沒有 MIN / TYP / MAX / UNIT / SYMBOL
   - 規則：（Figure caption 或「視圖字樣 + 腳位樣式」）且沒有規格表頭 → 轉成圖
2. 轉換：`add_picture`（同一個 prov／bbox、掛上 caption）→ `delete_items` 刪掉原表格 → 把 picture 移回原本的閱讀順序位置；
   `meta.classification = pin_map`；`meta.json` 記錄 `table→pin_map` 與判斷原因。
3. 後續沿用圖的流程：檢視器顯示裁切圖；`figures.kinds` 加入 pin assignment / pad assignment / ball assignment / pinout → kind = pinout。
   Granite Vision 只寫一行摘要（封裝、球數、有哪些視圖），**不列腳位**（理由見 2a）。
4. 驗證：W25Q128JV Figure 1a–1e、MC9S08SC4 腳位圖、CCG6 Figure 7–8（QFN）；golden 圖的「找到」比例應上升，規格表的 fidelity 不得下降。

預估：半天。

## 2a. 腳位清單改由 PDF 座標配對產生（原「選做」，依實驗結果改為必做）

腳位／球位清單（`pin_map`）由程式依 PDF 文字座標產生，不交給 VLM 列舉。

做法：
1. 切視圖：依 "Top View" / "Bottom View" / "Package Code X" 標題或面板之間的大間隙，把一張圖切成多個視圖，各自處理（Figure 1d 兩個封裝、Figure 1e 上視／底視）。
2. 配對：
   - BGA／WLCSP：每個球號（A1…H8）配對正下方（或正上方）最近的文字。
   - SOIC／QFN：每個腳位編號配對同一列、同一側最近的訊號名稱。
   - 依位置配對，不依順序，所以鏡像的 Bottom View 不受影響。
3. 檢查：
   - 同一視圖內球號重複 → flag（Figure 1e Bottom View 印成 F3 F3 F2 F1，datasheet 本身的筆誤）
   - Top View 與 Bottom View 同一球號的訊號不同 → flag
   - 與 Pin／Ball Description 表格（W25Q128JV 3.3／3.5／3.7／3.9）交叉比對，不一致 → flag
4. 輸出：picture 的 `meta.pin_map = [{"view": "Top View", "package": "Y", "pin": "B2", "signal": "VCC"}, …]`，
   附 `source = "pdf_text_position"`；檢視器在圖下方顯示這張清單。

證據（實驗 `scripts/exp_ballmap.py`，Figure 1d，人工計分）：
| 做法 | Package B（24） | Package C（24） |
|---|---|---|
| 現行（圖 + 攤平的 PDF 文字）| 列出兩個封裝球號的聯集（B 多出 A1），訊號沒有配對 | 同左 |
| 只給圖、現行 prompt | 23/24（漏 A5、誤稱有 A1） | 19/24（整列 F 遺漏、多出不存在的第 5 欄） |
| 只給圖、要求 BALL=SIGNAL 格式 | 0（重複輸出 NC 數百次） | 0 |
| 每個封裝各一張裁圖 | 0（只列球號、沒有訊號） | 0 |

Figure 1e（現行做法）：Top View 24/24 正確；Bottom View 是鏡像（A4 A3 A2 A1），模型照遞增順序對應 → B2／B3、C 列對調；
輸出在 300 token 處被截斷；datasheet 的 F3 重複未被發現。

結論：2B VLM 的錯誤（漏球、多出球、整列遺漏、鏡像對調）正好是腳位圖最不能錯的地方，且輸出沒有任何跡象可判斷哪裡錯。

預估：1 天（含 4 份 datasheet 的腳位圖驗證）。

## 4. 【錯誤，建議優先】pdfplumber 依框線重建表格時，外框被當成一個巨大儲存格

現象：W25Q128JV p69「10.2 16-Pin SOIC 300-mil」尺寸表，hybrid 輸出中第一格包含整張表的文字
（"Millimeters Inches Symbol Min Nom Max … A 2.36 2.49 …"），其餘格子疊在它上面，檢視器畫成表中表。
Docling 原本的格子是對的（14×7），hybrid 卻改用了 pdfplumber 的結果。

原因：
- `pdf_ruled_tables.table_to_cells`（原 `stage1_pdfplumber._table_to_cells`）把 pdfplumber 找到的每個矩形都當成儲存格。表格外圍的框（圖面外框／底色框）也構成一個矩形，
  於是多出一列、一欄，以及一個橫跨 r0–9、c0–8 的「儲存格」，內含框內全部文字，和真正的格子重疊。
- hybrid 的雙路比對有抓到（與 Docling 數字 token 差異 34.9%，flag = True），但 flag 只做標記，仍採用了壞掉的結果。
- golden 參數都不在封裝尺寸表，所以分數沒有反映。

影響範圍（`scripts/scan_overlap_cells.py`，儲存格重疊的表）：
| Datasheet | pdfplumber | Docling | hybrid |
|---|---|---|---|
| W25Q128JV | 1 張（p73，2 格） | 0 | 1 張（p69，56 格） |
| RT3624LE | 0 | 0 | 0 |
| CCG6 | 1 張（p14，1 格） | 0 | 1 張（p59，1 格） |
| MC9S08SC4 | 1 張（p8，6 格） | 0 | 1 張（p8，6 格；Table 3-3 Thermal，golden θJA 仍正確） |

做法：
1. `_table_to_cells`：移除「外框儲存格」（範圍內包含 ≥ 2 個其他儲存格中心的矩形），再用剩下的儲存格重新計算列／欄邊界，
   刪掉沒有儲存格使用的邊界。
2. hybrid 採用框線結果前的檢查：任何格位被 > 1 個儲存格覆蓋，或單一儲存格覆蓋 > 30% 的格位 → 不採用，改走 Docling 格線路徑；
   原因寫進 `meta.json`。
3. 測試：
   - 單元測試：合成一個「外框 + 2×2 表格」，確認外框被移除。
   - 回歸檢查：`scan_overlap_cells.py out\review` 對 4 份 datasheet 的 hybrid 輸出必須是 0。
   - golden 分數不得下降。

預估：2–3 小時（含重跑 4 份 datasheet 的 hybrid 表格部分；不需重跑圖片描述）。

## 3. 圖片描述的 prompt 不再帶入攤平的 PDF 文字

現象：hybrid 把圖範圍內的 PDF 文字 `" ".join(text.split())` 攤成一行放進 prompt。
並排的圖（兩個封裝、上視／底視）文字會逐行交錯，攤平後連換行都沒有，模型拿到的是錯誤的對應關係。
實驗中這反而讓結果變差（Figure 1d：只給圖 23/24，給攤平文字後球號變成兩個封裝的聯集）。

做法：
1. 預設只給圖與 caption；或給保留版面的文字（依大間隙切欄、保留換行），兩種都用 golden 圖抽樣比較後決定。
2. 腳位圖（kind = pinout）不給文字、只要摘要（見 2a）。
3. `describe_max_new_tokens` 依 kind 調整，避免在列舉中途被截斷；或改為只要求摘要。
4. 檢視器與 JSON 標示描述來源：「model description, unverified」。

預估：半天（含抽樣比較）。
