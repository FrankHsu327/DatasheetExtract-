# Golden set

每份 datasheet 一個 `<stem>.golden.json`，由人工從 PDF 填寫，作為評估的標準答案。

```json
{
  "datasheet": "W25Q32JV.pdf",
  "parameters": [
    {"symbol": "VIH", "conditions": null, "min": "0.7 x VCC", "max": "VCC+0.4", "unit": "V"},
    {"symbol": "tCLQV", "conditions": "CL = 30pF", "max": "6", "unit": "ns"}
  ]
}
```

填寫原則
- 只填 EA 會用到的參數即可（約 20–40 個），不必整份抄
- 數值照 PDF 原文抄（含 `0.7 x VCC` 這類表達式），不要換算
- 同一 symbol 有多種條件（不同 VCC、不同頻率）就分多筆，conditions 寫清楚
- 只寫有的欄位；沒有 typ 就不要放 typ 這個 key

建議份數：每類元件 5 份，涵蓋不同廠牌（Winbond / Macronix / GigaDevice …），
因為不同廠牌的表格排版差異就是主要的遺漏來源。

評估：
```bash
python -m datasheet_extractor evaluate out/X/X.component.json golden/X.golden.json \
       --docling-json out/X/01_docling/document.json
```
