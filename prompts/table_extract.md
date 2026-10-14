You are given ONE table from an electronic component datasheet.
Table caption: {{CAPTION}}
Section: {{SECTION}}
Category (auto-detected, may be wrong): {{CATEGORY}}

Table (every row has a row_id in the first column):

{{TABLE_MARKDOWN}}

Table footnotes:
{{FOOTNOTES}}

Rows to process: {{ROW_IDS}}

TASK
For EVERY row to process, output exactly one of:
  (a) an entry in "parameters" if the row defines a specification value, or
  (b) an entry in "ignored_rows" with a short reason (e.g. "section heading", "header", "free text").
A row_id must never be missing. Do not merge rows. Do not split one row into several entries.

RULES
- Copy values VERBATIM from the cell text (keep the original string, e.g. "0.7 x VCC", "2.0(1)").
  Do not convert units, do not compute, do not fill in values that are not in that row.
- If a cell is empty or "-", use null.
- If the parameter name / conditions are visually merged from a row above, you may repeat them.
- "conditions" = test conditions for that row (e.g. "VCC = 3.6V, fC = 104MHz"), else null.
- "unit" = the unit that applies to min/typ/max/value in that row.

OUTPUT: pure JSON, no markdown fences, no comments:
{
  "parameters": [
    {"row_id": "T3.R5", "name": "...", "symbol": "...", "conditions": "...",
     "min": "...", "typ": "...", "max": "...", "value": null, "unit": "..."}
  ],
  "ignored_rows": [ {"row_id": "T3.R0", "reason": "section heading"} ]
}
