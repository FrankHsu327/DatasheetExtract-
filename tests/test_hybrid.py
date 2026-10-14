from collections import Counter

from datasheet_extractor.stage1_hybrid import _bands, _disagreement, _num_tokens


def _cell(r, c, l, t, rr, b, text="", rs=1, cs=1):
    return {"bbox": {"l": l, "t": t, "r": rr, "b": b}, "start_row_offset_idx": r, "end_row_offset_idx": r + rs,
            "start_col_offset_idx": c, "end_col_offset_idx": c + cs, "text": text}


def test_column_bands_use_midpoints_between_docling_cells():
    cells = [_cell(0, 0, 10, 0, 40, 10), _cell(0, 1, 60, 0, 80, 10), _cell(0, 2, 100, 0, 130, 10)]
    xs = _bands(cells, 3, "l", "r", "start_col_offset_idx", "end_col_offset_idx", (0, 150))
    assert xs == [0, 50, 90, 150]


def test_band_without_any_cell_is_interpolated():
    cells = [_cell(0, 0, 10, 0, 40, 10), _cell(0, 2, 100, 0, 130, 10)]   # column 1 has no bbox at all
    xs = _bands(cells, 3, "l", "r", "start_col_offset_idx", "end_col_offset_idx", (0, 150))
    assert xs[0] == 0 and xs[-1] == 150 and xs[1] < xs[2]


def test_numeric_disagreement():
    a = _num_tokens([{"text": "-0.5 to 6"}, {"text": "V"}])
    assert _disagreement(a, a) == 0.0
    assert _disagreement(a, Counter()) == 1.0
