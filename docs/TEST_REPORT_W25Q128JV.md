# 實測報告：Winbond W25Q128JV（Rev G, 2019-04-08, 78 頁）

> 歷史紀錄：本報告是早期以 pdfplumber 後端做的實測。pdfplumber／Docling 單獨使用的後端與 `--backend` 參數已移除，
> 目前 Stage 1 只有 hybrid（見 `docs/METHOD_COMPARISON.md`）。報告中修正的 Stage 2–4 規則仍在使用。

## 測試條件

- **Stage 1 用 pdfplumber 後端，不是 Docling**：測試環境連不到 HuggingFace，無法下載 Docling 的 layout 與 TableFormer 模型。
  - 本次驗證的是 **Stage 2–4 的規則能否應付真實排版**，不代表 Docling 本身的表格辨識品質。
  - 在公司環境用 `--backend docling` 跑同一份檔案後，兩者的差異就是 Docling 的貢獻或遺漏。
- **Golden set 獨立建立**：依 `pdftotext -layout` 原文手抄 9.1–9.6 的 59 個參數，抄寫時沒有參考程式輸出。
- **評估器先做 mutation test**：故意改錯 2 個值、刪掉 1 筆，三者都被抓到，且遺漏歸因正確。

## 結果

| 項目 | 第一次執行 | 修正後 |
|---|---|---|
| Spec 表覆蓋率 | Abs Max 0%（欄位無法辨識） | 6 張表全部 100% |
| AC 表跨頁合併 | 未合併，註腳找不到 | 已合併，note 1–6 全部掛上 |
| 抽取參數數量 | 140（含封裝尺寸 73 筆） | 67 |
| 關鍵參數清單 | 全數找到，但有誤配 | 18/18，無誤配 |
| diagnose 可疑項 | 182 | 3（皆為 Features 段的真實規格文字） |
| Golden recall | — | **59/59** |
| 執行時間 | 約 25 秒（78 頁，無 GPU） | |

## 發現並修正的問題

| # | 現象 | 根因 | 修正 |
|---|---|---|---|
| 1 | Abs Max 整張表未抽 | 表頭是複數 `PARAMETERS`，值欄叫 `RANGE` | 角色比對允許複數；`range` 加入 value 關鍵字 |
| 2 | `ALT` 欄被當未知欄，所有 AC 參數都被標 flag | Winbond 有替代符號欄（tCSS、tHO…） | 新增 `alt_symbol` 角色，關鍵參數比對也會查 alt |
| 3 | AC 表跨頁沒合併，註腳全部找不到 | 兩段表格之間只有一行「Continued – next page」，沒有 caption | 兩表之間的文字含 continued 字樣，也視為延續訊號 |
| 4 | 封裝尺寸表（mm/inch Min/Nom/Max）被當規格抽取 | 「有 min/max 欄就抽」的規則太寬 | 新增 `package` 類別；已分類為非 spec 的表不抽 |
| 5 | 9.5 的值「0.1 VCC to 0.9 VCC」被複製到 min 和 max | 一格合併橫跨 MIN/MAX 兩欄 | 依原始儲存格 origin 判斷，橫跨多欄的值視為單一 value |
| 6 | 單位 `V/ns`、時脈下限 `D.C.` 無法解析 | 單位表不足 | 補上；`D.C.` 視為 0 Hz（原文保留在 raw） |
| 7 | 三筆 ICC3（50/80/104MHz）互相標成衝突 | 衝突比對沒考慮參數名稱 | 名稱納入衝突比對的 key |
| 8 | `icc_standby` 誤配到 tRES1（名稱含 "Standby Mode"）等 | 名稱關鍵字太短，且跨類別比對 | 只在預期的表格類別內比對；關鍵字加長 |
| 9 | diagnose 報出 182 個表外數字區 | 時序圖的 bit 編號、目錄頁碼都算進去 | 只計算帶小數或單位的「規格值 token」；排除目錄點線與 figure 範圍 |
| 10 | `1 2 8 M - bit`（字距加寬的文字被切開） | 儲存格取字的 x_tolerance 太小 | 2 → 3（crosscheck 正確抓到這個問題） |

## 仍存在、程式無法單獨解決的問題

這些項目都已標 flag，會出現在 `review.html`：

- **條件寫在參數名稱裡**：例如「Clock frequency … (3.0V-3.6V)」，conditions 欄是空的。這類情況適合交給 LLM 拆解，或在 EA 端用名稱比對。
- **PDF 本身的下標遺失**：AC Measurement 表的 `V_IN` 只剩 `IN`，pdftotext 讀出來也一樣，是 PDF 文字層的問題。目前會被 `unit_mismatch` 標出。
- **非數值規格**：`45% PC`、`0.7 x VCC`、`See Note (2)` 保留為 `expr`，需要人或 LLM 解讀。
- **斜率參數用 t 開頭**：tCLCH / tCHCL 的單位是 V/ns，會被標 `unit_mismatch_for_time`。這是 datasheet 的寫法，屬於合理提醒。
- **時序圖被誤判為表格**（p.62、p.26）：pdfplumber 後端已用「非空格比例」過濾掉大部分，剩下的不會進入抽取，只出現在 crosscheck 結果裡。

## 下一步建議

1. 在公司環境用 `--backend docling` 跑同一份檔案，再跑 `evaluate`，比較兩個後端的 recall。
2. 再挑 2–3 份不同廠牌的 datasheet（Macronix MX25、GigaDevice GD25）各寫一份 golden set。Winbond 的排版規則（ALT 欄、Continued 標示）不一定適用其他廠牌。
3. 串上 LLM 後，優先處理「條件寫在名稱裡」這類情況。
