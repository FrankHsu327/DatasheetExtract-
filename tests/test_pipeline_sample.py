import json

from datasheet_extractor.evaluate import evaluate_files
from datasheet_extractor.pipeline import run_from_docling_json


def test_end_to_end(cfg, sample_paths, tmp_path):
    pdf, dj, gold = sample_paths
    comp = run_from_docling_json(dj, tmp_path, cfg, pdf_path=pdf, source_name=pdf.name)
    q = comp["quality"]
    assert q["validation"]["schema_errors"] == 0
    assert comp["component"]["part_numbers"] == ["DS325Q32"]
    # 模擬 Docling 漏掉 tCLQX → 三道防線都應該抓到
    assert "t_out_hold" in q["expected_parameters"]["missing"]
    ac_xc = next(c for c in q["crosscheck"] if c["table_id"] == "T3")
    assert not ac_xc["pass"] and "1.5" in ac_xc["missing_tokens"]
    fig = next(f for f in comp["figures"] if f["kind"] == "timing_diagram")
    assert any("tCLQX" in f for f in fig["flags"])
    assert q["needs_review"] is True
    assert (tmp_path / "review.html").exists()

    res = evaluate_files(tmp_path / f"{pdf.stem}.component.json", gold, dj)
    assert res["status_count"] == {"ok": 18, "lost_in_docling": 1}
    assert res["details"][[d["symbol"] for d in res["details"]].index("tCLQX")]["status"] == "lost_in_docling"


def test_abs_max_range_split(cfg, sample_paths, tmp_path):
    pdf, dj, _ = sample_paths
    comp = run_from_docling_json(dj, tmp_path, cfg, pdf_path=pdf)
    vcc = next(p for p in comp["parameters"] if p["category"] == "absolute_max" and p["symbol"] == "VCC")
    assert vcc["min"]["value"] == -0.5 and vcc["max"]["value"] == 4.0 and vcc["value"]["raw"] == "-0.5 to 4.0"


def test_diagnose_detects_undetected_table(cfg, sample_paths):
    """模擬 Layout 層把整張 AC 表漏掉 → diagnose 應在 PDF 文字層找到表外的數字密集區。"""
    from datasheet_extractor.diagnose import diagnose
    from datasheet_extractor.docling_reader import DoclingDoc
    from datasheet_extractor.stage2_tables import extract_tables

    pdf, dj, _ = sample_paths
    data = json.loads(dj.read_text(encoding="utf-8"))
    data["body"]["children"] = [c for c in data["body"]["children"] if c["$ref"] != "#/tables/4"]
    doc = DoclingDoc(data)
    tables, _ = extract_tables(doc, cfg)
    rep = diagnose(doc, pdf, tables)
    regions = [s for s in rep["suspects"] if s["type"] == "numeric_region_outside_tables"]
    assert any(r["page"] == 2 for r in regions)
    clean = diagnose(DoclingDoc.load(dj), pdf, extract_tables(DoclingDoc.load(dj), cfg)[0])
    assert not [s for s in clean["suspects"] if s["type"] == "numeric_region_outside_tables"]
