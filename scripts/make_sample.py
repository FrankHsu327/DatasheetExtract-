"""產生測試用的假 datasheet PDF + 模擬的 Docling 輸出 + golden set。

用途：在沒有 docling 模型（例如 Devin 環境連不到 HuggingFace）時，也能端對端測試 Stage 2~4。
模擬 Docling 的常見缺陷：
  - DC 表跨頁（第二段 caption 寫 Continued、表頭重複）
  - AC 表多層表頭（Limits 橫跨 Min/Typ/Max）、section row、合併儲存格造成的空白（需 fill-down）
  - 註腳上標黏在數值上（10(1)）
  - 刻意在模擬的 Docling 輸出中「漏掉」AC 表一列（tCLQX）→ crosscheck 與 evaluate 應該抓到

執行：python scripts/make_sample.py   → samples/ 與 golden/
"""
from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
GOLDEN = ROOT / "golden"
W, H = letter
ROW_H = 16
X0 = 50

ABS_MAX = {
    "caption": "Table 1. Absolute Maximum Ratings",
    "cols": [170, 60, 110, 50],
    "header": [["Parameter", "Symbol", "Rating", "Unit"]],
    "rows": [
        ["Supply Voltage", "VCC", "-0.5 to 4.0", "V"],
        ["Storage Temperature", "TSTG", "-65 to 150", "°C"],
        ["ESD (Human Body Model)", "VESD", "2000", "V"],
    ],
}
REC_OP = {
    "caption": "Table 2. Recommended Operating Conditions",
    "cols": [170, 60, 50, 50, 50, 50],
    "header": [["Parameter", "Symbol", "Min", "Typ", "Max", "Unit"]],
    "rows": [
        ["Supply Voltage", "VCC", "2.7", "3.0", "3.6", "V"],
        ["Ambient Temperature", "TA", "-40", "", "85", "°C"],
    ],
}
DC_HDR = [["Parameter", "Symbol", "Conditions", "Min", "Typ", "Max", "Unit"]]
DC_COLS = [120, 45, 120, 40, 40, 55, 35]
DC_P1 = [
    ["Input High Voltage", "VIH", "", "0.7 x VCC", "", "VCC+0.4", "V"],
    ["Input Low Voltage", "VIL", "", "-0.5", "", "0.3 x VCC", "V"],
    ["Output High Voltage", "VOH", "IOH = -100 µA", "VCC-0.2", "", "", "V"],
    ["Output Low Voltage", "VOL", "IOL = 1.6 mA", "", "", "0.4", "V"],
]
DC_P2 = [
    ["Standby Current", "ICC1", "CS# = VCC", "", "10", "50(1)", "µA"],
    ["Read Current", "ICC3", "fC = 104 MHz", "", "15", "25", "mA"],
    ["Input Leakage", "ILI", "", "", "", "±2", "µA"],
]
AC_HDR = [["Parameter", "Symbol", "Limits", "", "", "Unit"], ["", "", "Min", "Typ", "Max", ""]]
AC_COLS = [150, 50, 45, 45, 45, 40]
AC_ROWS = [
    ["Read Mode", "", "", "", "", ""],                                    # section row
    ["Clock Frequency", "fC", "", "", "104", "MHz"],
    ["Clock High, Low Time", "tCH", "4.5", "", "", "ns"],
    ["", "tCL", "4.5", "", "", "ns"],                                     # merged parameter cell
    ["Data In Setup Time", "tDVCH", "2", "", "", "ns"],
    ["Data In Hold Time", "tCHDX", "3", "", "", "ns"],
    ["CS# Active Setup Time", "tSLCH", "5", "", "", "ns"],
    ["CS# Active Hold Time", "tCHSH", "5", "", "", "ns"],
    ["CS# Deselect Time", "tSHSL", "50", "", "", "ns"],
    ["Clock Low to Output Valid", "tCLQV", "", "", "6", "ns"],
    ["Output Hold Time", "tCLQX", "1.5", "", "", "ns"],                   # ← 模擬 Docling 漏掉這列
    ["Power-up Timing", "", "", "", "", ""],                              # section row
    ["VCC(min) to CS# Low", "tVSL", "300", "", "", "µs"],
]
DROPPED_AC_ROW = "tCLQX"


def _draw_table(c: canvas.Canvas, x: float, y_top: float, cols, header, rows, spans=()):
    data = header + rows
    t = Table(data, colWidths=cols, rowHeights=[ROW_H] * len(data))
    style = [("GRID", (0, 0), (-1, -1), 0.5, colors.black), ("FONTSIZE", (0, 0), (-1, -1), 7.5),
             ("BACKGROUND", (0, 0), (-1, len(header) - 1), colors.lightgrey),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
    style += [("SPAN", a, b) for a, b in spans]
    t.setStyle(TableStyle(style))
    h = ROW_H * len(data)
    t.wrapOn(c, W, H)
    t.drawOn(c, x, y_top - h)
    return y_top - h


def make_pdf(path: Path) -> dict:
    """Draw PDF; return layout info used to build the simulated Docling JSON."""
    layout: dict = {"pages": {}}
    c = canvas.Canvas(str(path), pagesize=letter)

    # ---------------- page 1
    y = H - 60
    c.setFont("Helvetica-Bold", 16); c.drawString(X0, y, "DS325Q32 3V 32M-bit Serial NOR Flash"); y -= 30
    blocks = []
    c.setFont("Helvetica-Bold", 11); c.drawString(X0, y, "1. Absolute Maximum Ratings"); blocks.append(("h", "1. Absolute Maximum Ratings", y)); y -= 18
    c.setFont("Helvetica", 9); c.drawString(X0, y, ABS_MAX["caption"]); blocks.append(("cap", ABS_MAX["caption"], y)); y -= 6
    bottom = _draw_table(c, X0, y, ABS_MAX["cols"], ABS_MAX["header"], ABS_MAX["rows"])
    blocks.append(("table", "abs", y, bottom)); y = bottom - 26
    c.setFont("Helvetica-Bold", 11); c.drawString(X0, y, "2. Recommended Operating Conditions"); blocks.append(("h", "2. Recommended Operating Conditions", y)); y -= 18
    c.setFont("Helvetica", 9); c.drawString(X0, y, REC_OP["caption"]); blocks.append(("cap", REC_OP["caption"], y)); y -= 6
    bottom = _draw_table(c, X0, y, REC_OP["cols"], REC_OP["header"], REC_OP["rows"])
    blocks.append(("table", "rec", y, bottom)); y = bottom - 26
    c.setFont("Helvetica-Bold", 11); c.drawString(X0, y, "3. DC Electrical Characteristics"); blocks.append(("h", "3. DC Electrical Characteristics", y)); y -= 18
    c.setFont("Helvetica", 9); cap = "Table 3. DC Characteristics (TA = -40 to 85 °C, VCC = 2.7 to 3.6 V)"
    c.drawString(X0, y, cap); blocks.append(("cap", cap, y)); y -= 6
    bottom = _draw_table(c, X0, y, DC_COLS, DC_HDR, DC_P1)
    blocks.append(("table", "dc1", y, bottom))
    layout["pages"][1] = blocks
    c.showPage()

    # ---------------- page 2
    y = H - 60
    blocks = []
    c.setFont("Helvetica", 9); cap = "Table 3. DC Characteristics (Continued)"
    c.drawString(X0, y, cap); blocks.append(("cap", cap, y)); y -= 6
    bottom = _draw_table(c, X0, y, DC_COLS, DC_HDR, DC_P2)
    blocks.append(("table", "dc2", y, bottom)); y = bottom - 14
    c.setFont("Helvetica", 8); note = "Notes: 1. Maximum value at TA = 85 °C. Not 100% tested."
    c.drawString(X0, y, note); blocks.append(("note", note, y)); y -= 28
    c.setFont("Helvetica-Bold", 11); c.drawString(X0, y, "4. AC Electrical Characteristics"); blocks.append(("h", "4. AC Electrical Characteristics", y)); y -= 18
    c.setFont("Helvetica", 9); cap = "Table 4. AC Characteristics"
    c.drawString(X0, y, cap); blocks.append(("cap", cap, y)); y -= 6
    spans = [((0, 0), (0, 1)), ((1, 0), (1, 1)), ((2, 0), (4, 0)), ((5, 0), (5, 1)),
             ((0, 2), (-1, 2)), ((0, 4), (0, 5)), ((0, 13), (-1, 13))]
    rows_drawn = [r[:] for r in AC_ROWS]
    rows_drawn[3][0] = ""  # merged
    bottom = _draw_table(c, X0, y, AC_COLS, AC_HDR, rows_drawn, spans)
    blocks.append(("table", "ac", y, bottom)); y = bottom - 30
    # timing diagram (simple waveform)
    fig_top = y
    c.setLineWidth(1)
    for i in range(6):
        x = X0 + 40 + i * 60
        c.line(x, y - 20, x + 30, y - 20); c.line(x + 30, y - 20, x + 30, y - 5); c.line(x + 30, y - 5, x + 60, y - 5); c.line(x + 60, y - 5, x + 60, y - 20)
    c.setFont("Helvetica", 7); c.drawString(X0, y - 15, "CLK"); c.drawString(X0, y - 45, "DO")
    c.line(X0 + 40, y - 45, X0 + 400, y - 45)
    c.drawString(X0 + 130, y - 60, "tCLQV"); c.drawString(X0 + 220, y - 60, "tCLQX")
    fig_bottom = y - 70
    c.setFont("Helvetica", 9); cap = "Figure 1. Serial Output Timing"
    c.drawString(X0, fig_bottom - 14, cap)
    blocks.append(("fig", cap, fig_top, fig_bottom, fig_bottom - 14))
    layout["pages"][2] = blocks
    c.showPage()

    # ---------------- page 3
    y = H - 60
    blocks = []
    c.setFont("Helvetica-Bold", 11); c.drawString(X0, y, "5. Typical Characteristics"); blocks.append(("h", "5. Typical Characteristics", y)); y -= 20
    c.rect(X0 + 20, y - 150, 250, 150); c.line(X0 + 20, y - 150, X0 + 270, y - 40)
    c.setFont("Helvetica", 9); cap = "Figure 2. Typical Standby Current vs. Temperature"
    c.drawString(X0, y - 166, cap)
    blocks.append(("fig", cap, y, y - 150, y - 166))
    layout["pages"][3] = blocks
    c.showPage()
    c.save()
    return layout


def _table_def(key: str):
    if key == "abs":
        return ABS_MAX["cols"], ABS_MAX["header"], ABS_MAX["rows"], []
    if key == "rec":
        return REC_OP["cols"], REC_OP["header"], REC_OP["rows"], []
    if key == "dc1":
        return DC_COLS, DC_HDR, DC_P1, []
    if key == "dc2":
        return DC_COLS, DC_HDR, DC_P2, []
    if key == "ac":
        rows = [r[:] for r in AC_ROWS]
        return AC_COLS, AC_HDR, rows, "ac"
    raise KeyError(key)


def make_docling_json(layout: dict, out: Path, drop_row: str | None = DROPPED_AC_ROW) -> None:
    from docling_core.types.doc import (BoundingBox, CoordOrigin, DocItemLabel, DoclingDocument,
                                        ProvenanceItem, Size, TableCell, TableData)

    doc = DoclingDocument(name="DS325Q32")
    for p in (1, 2, 3):
        doc.add_page(page_no=p, size=Size(width=W, height=H))

    def prov(page, l, t, r, b):
        return ProvenanceItem(page_no=page, bbox=BoundingBox(l=l, t=t, r=r, b=b, coord_origin=CoordOrigin.BOTTOMLEFT),
                              charspan=(0, 0))

    first = True
    for page, blocks in layout["pages"].items():
        pending_caption = None
        for blk in blocks:
            kind = blk[0]
            if kind == "h":
                if first:
                    doc.add_text(label=DocItemLabel.TITLE, text="DS325Q32 3V 32M-bit Serial NOR Flash",
                                 prov=prov(page, X0, H - 48, 400, H - 64))
                    first = False
                doc.add_heading(text=blk[1], level=1, prov=prov(page, X0, blk[2] + 11, 400, blk[2] - 2))
            elif kind == "cap":
                pending_caption = doc.add_text(label=DocItemLabel.CAPTION, text=blk[1],
                                               prov=prov(page, X0, blk[2] + 9, 450, blk[2] - 2))
            elif kind == "note":
                doc.add_text(label=DocItemLabel.TEXT, text=blk[1], prov=prov(page, X0, blk[2] + 8, 450, blk[2] - 2))
            elif kind == "table":
                cols, header, rows, special = _table_def(blk[1])
                top, bottom = blk[2], blk[3]
                data_rows = header + rows
                xs = [X0]
                for w_ in cols:
                    xs.append(xs[-1] + w_)
                cells = []
                skip_rows = set()
                if special == "ac" and drop_row:
                    skip_rows = {len(header) + i for i, r in enumerate(rows) if r[1] == drop_row}
                out_r = 0
                for r_idx, row in enumerate(data_rows):
                    if r_idx in skip_rows:
                        continue
                    y_t = top - r_idx * ROW_H
                    y_b = y_t - ROW_H
                    is_hdr = r_idx < len(header)
                    c_idx = 0
                    while c_idx < len(row):
                        text = row[c_idx]
                        rs, cs = 1, 1
                        if special == "ac":
                            if r_idx == 0 and c_idx in (0, 1, 5):
                                rs = 2
                            if r_idx == 0 and c_idx == 2:
                                cs = 3
                            if r_idx == 1 and c_idx in (0, 1, 5):
                                c_idx += 1
                                continue
                            sec = r_idx - len(header)
                            if 0 <= sec < len(rows) and rows[sec][0] and not any(rows[sec][1:]):
                                cells.append(TableCell(text=text, row_span=1, col_span=len(row),
                                                       start_row_offset_idx=out_r, end_row_offset_idx=out_r + 1,
                                                       start_col_offset_idx=0, end_col_offset_idx=len(row),
                                                       column_header=False, row_section=True,
                                                       bbox=BoundingBox(l=xs[0], t=y_t, r=xs[-1], b=y_b,
                                                                        coord_origin=CoordOrigin.BOTTOMLEFT)))
                                break
                        cells.append(TableCell(text=text, row_span=rs, col_span=cs,
                                               start_row_offset_idx=out_r, end_row_offset_idx=out_r + rs,
                                               start_col_offset_idx=c_idx, end_col_offset_idx=c_idx + cs,
                                               column_header=is_hdr,
                                               bbox=BoundingBox(l=xs[c_idx], t=y_t, r=xs[c_idx + cs], b=y_t - rs * ROW_H,
                                                                coord_origin=CoordOrigin.BOTTOMLEFT)))
                        c_idx += cs
                    out_r += 1
                data = TableData(num_rows=out_r, num_cols=len(cols), table_cells=cells)
                doc.add_table(data=data, caption=pending_caption, prov=prov(page, xs[0], top, xs[-1], bottom))
                pending_caption = None
            elif kind == "fig":
                cap_item = doc.add_text(label=DocItemLabel.CAPTION, text=blk[1],
                                        prov=prov(page, X0, blk[4] + 9, 450, blk[4] - 2))
                pic = doc.add_picture(caption=cap_item, prov=prov(page, X0, blk[2], 460, blk[3]))
                if "Timing" in blk[1]:
                    for s in ("CLK", "DO", "tCLQV", "tCLQX"):
                        doc.add_text(label=DocItemLabel.TEXT, text=s, parent=pic)
    out.write_text(json.dumps(doc.export_to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")


GOLDEN_PARAMS = [
    {"symbol": "VCC", "conditions": None, "min": "2.7", "typ": "3.0", "max": "3.6", "unit": "V"},
    {"symbol": "TA", "min": "-40", "max": "85", "unit": "°C"},
    {"symbol": "VIH", "min": "0.7 x VCC", "max": "VCC+0.4", "unit": "V"},
    {"symbol": "VIL", "min": "-0.5", "max": "0.3 x VCC", "unit": "V"},
    {"symbol": "VOH", "conditions": "IOH = -100 µA", "min": "VCC-0.2", "unit": "V"},
    {"symbol": "VOL", "conditions": "IOL = 1.6 mA", "max": "0.4", "unit": "V"},
    {"symbol": "ICC1", "conditions": "CS# = VCC", "typ": "10", "max": "50", "unit": "µA"},
    {"symbol": "ICC3", "conditions": "fC = 104 MHz", "typ": "15", "max": "25", "unit": "mA"},
    {"symbol": "fC", "max": "104", "unit": "MHz"},
    {"symbol": "tCH", "min": "4.5", "unit": "ns"},
    {"symbol": "tCL", "min": "4.5", "unit": "ns"},
    {"symbol": "tDVCH", "min": "2", "unit": "ns"},
    {"symbol": "tCHDX", "min": "3", "unit": "ns"},
    {"symbol": "tSLCH", "min": "5", "unit": "ns"},
    {"symbol": "tCHSH", "min": "5", "unit": "ns"},
    {"symbol": "tSHSL", "min": "50", "unit": "ns"},
    {"symbol": "tCLQV", "max": "6", "unit": "ns"},
    {"symbol": "tCLQX", "min": "1.5", "unit": "ns"},
    {"symbol": "tVSL", "min": "300", "unit": "µs"},
]


def main():
    SAMPLES.mkdir(exist_ok=True)
    GOLDEN.mkdir(exist_ok=True)
    pdf = SAMPLES / "DS325Q32.pdf"
    layout = make_pdf(pdf)
    make_docling_json(layout, SAMPLES / "DS325Q32.docling.json")
    (GOLDEN / "DS325Q32.golden.json").write_text(json.dumps(
        {"datasheet": "DS325Q32.pdf", "parameters": GOLDEN_PARAMS}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {pdf}, simulated docling json, golden set")


if __name__ == "__main__":
    main()
