from datasheet_extractor.docling_reader import DoclingDoc
from datasheet_extractor.stage2_tables import detect_role, extract_tables, parse_note_block
from datasheet_extractor.stage3_locate import locate


def test_detect_role(cfg):
    kw = cfg["tables"]["header_keywords"]
    assert detect_role("Limits / Min", kw) == "min"
    assert detect_role("Max (ns)", kw) == "max"
    assert detect_role("Test Conditions", kw) == "conditions"
    assert detect_role("Parameter", kw) == "parameter"


def test_parameter_column_is_symbol_when_description_present(cfg):
    from datasheet_extractor.stage2_tables import _assign_roles
    kw = cfg["tables"]["header_keywords"]
    # Infineon Table 4/5：Spec ID | Parameter | Description | Min | Typ | Max | Unit | Details/conditions
    roles = _assign_roles(["Spec ID", "Parameter", "Description", "Min", "Typ", "Max", "Unit", "Details/conditions"], kw)
    assert roles[:3] == ["other", "symbol", "parameter"] and roles[-1] == "conditions"
    # 一般表格不受影響
    assert _assign_roles(["Parameter", "Symbol", "Min", "Max"], kw)[:2] == ["parameter", "symbol"]


def test_note_block():
    assert parse_note_block("Notes: 1. Max at 85C. 2. Guaranteed by design.") == {
        "1": "Max at 85C.", "2": "Guaranteed by design."}


def test_sample_tables(cfg, sample_paths):
    _, dj, _ = sample_paths
    tables, log = extract_tables(DoclingDoc.load(dj), cfg)
    locate(tables, cfg)
    assert log["raw_table_count"] == 5
    assert len(tables) == 4, "DC 跨頁表應合併"
    dc = tables[2]
    assert dc["category"] == "dc_characteristics"
    assert dc["pages"] == [1, 2]
    assert "1" in dc["footnotes"]
    ac = tables[3]
    assert [c["role"] for c in ac["columns"]] == ["parameter", "symbol", "min", "typ", "max", "unit"]
    kinds = [r["kind"] for r in ac["rows"]]
    assert kinds.count("section") == 2
    tcl = next(r for r in ac["rows"] if r["cells"][1] == "tCL")
    assert tcl["cells"][0] == "Clock High, Low Time" and tcl["filled"] == [0]


def test_conditions_not_filled_into_named_row(cfg, sample_paths):
    _, dj, _ = sample_paths
    tables, _ = extract_tables(DoclingDoc.load(dj), cfg)
    ili = next(r for r in tables[2]["rows"] if r["cells"][1] == "ILI")
    assert ili["cells"][2] == ""
