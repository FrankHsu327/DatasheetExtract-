from datasheet_extractor.text_normalize import (normalize_text, numeric_tokens, parse_range, parse_unit,
                                                parse_value, split_footnotes, unit_from_header)


def test_micro_and_minus_unified():
    assert normalize_text("10 μA") == "10 µA"
    assert normalize_text("∆VUVLO") == "ΔVUVLO"
    assert normalize_text("\u22120.5") == "-0.5"


def test_footnote_not_glued_to_value():
    assert parse_value("2.0(1)")["value"] == 2.0
    assert parse_value("8¹", "ns")["notes"] == ["1"]
    assert parse_value("3.6 Note 2", "V")["value"] == 3.6
    assert split_footnotes("(1)") == ("(1)", [])          # 整格只有註腳編號時不拆


def test_units_and_si():
    v = parse_value("10", "µA")
    assert v["si_unit"] == "A" and abs(v["value_si"] - 1e-5) < 1e-15
    assert parse_unit("MHz")["factor"] == 1e6
    assert parse_unit("°C")["si_unit"] == "°C"
    assert parse_unit("Mb")["si_unit"] == "bit"
    assert unit_from_header("Max (ns)") == "ns"


def test_expression_kept_raw():
    v = parse_value("0.7 x VCC", "V")
    assert v["value"] is None and v["expr"] == "0.7 x VCC" and v["si_unit"] == "V"


def test_empty_and_dash():
    assert parse_value("—") is None
    assert parse_value("") is None


def test_range_and_thousands():
    assert parse_range("-0.5 to 4.0") == ("-0.5", "4.0", None)
    assert parse_value("100,000 cycles")["value"] == 100000


def test_numeric_tokens_ignore_part_numbers():
    assert numeric_tokens("W25Q32 at 2.70 V") == ["2.7"]


def test_latex_from_vlm_backends():
    assert split_footnotes(normalize_text(" $t_{VSL}^{(1)}$ ")) == ("tVSL", ["1"])
    assert normalize_text("F$_{R}$ = 133MHz") == "FR = 133MHz"
    assert normalize_text("$T_{A} = 25^{\\circ}$ C") == "TA = 25° C"
    assert normalize_text("IVCC_PS4 at $V_{IN}$") == "IVCC_PS4 at VIN"     # 數學模式外的底線不動
    assert normalize_text("$\\pm 2$") == "±2"
    assert normalize_text("a) $\\mathsf { V _ { D D } } = 5 \\mathsf { V } ,$ High Drive") == "a) VDD = 5V, High Drive"
    assert normalize_text("I/O_Leakage") == "I/O_Leakage"          # 沒有 $ 或反斜線的文字不動
