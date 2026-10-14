"""以 FakeLLMClient 驗證 LLM 路徑：覆蓋率強制、缺列重送、數值必須存在於原文。
Devin 串好 CompanyLLMClient 後，這個測試仍應通過（它不打真的 API）。"""
import json

from datasheet_extractor.llm_client import FakeLLMClient
from datasheet_extractor.stage3_extract import coverage_of, llm_extract


def _table():
    rows = [
        ["Clock Frequency fC", "104", "MHz"],
        ["Output Hold tCLQX", "1.5", "ns"],
        ["Some free text row", "", ""],
    ]
    return {"id": "T9", "caption": "Table 9. Timing", "category": "ac_characteristics", "section_path": [],
            "pages": [3], "footnotes": {},
            "columns": [{"index": i, "header": "", "role": "other", "unit_hint": None} for i in range(3)],
            "rows": [{"row_id": f"T9.R{i}", "cells": r, "kind": "data", "section": None,
                      "source_ref": "#/tables/9", "source_row": i, "filled": []} for i, r in enumerate(rows)],
            "flags": []}


def test_llm_retry_and_coverage(cfg):
    first = {"parameters": [{"row_id": "T9.R0", "name": "Clock Frequency", "symbol": "fC", "max": "104", "unit": "MHz"}],
             "ignored_rows": [{"row_id": "T9.R2", "reason": "free text"}]}
    second = {"parameters": [{"row_id": "T9.R1", "name": "Output Hold", "symbol": "tCLQX", "min": "1.6", "unit": "ns"}],
              "ignored_rows": []}
    client = FakeLLMClient([json.dumps(first), json.dumps(second)])
    t = _table()
    params, mapping = llm_extract(t, client, "{{TABLE_MARKDOWN}}\n{{ROW_IDS}}", cfg)
    assert len(client.calls) == 2 and "T9.R1" in client.calls[1]["user"]
    assert mapping == {"T9.R0": "parameter", "T9.R1": "parameter", "T9.R2": "ignored:free text"}
    assert coverage_of(t, mapping)["coverage"] == 1.0
    hall = next(p for p in params if p["symbol"] == "tCLQX")
    assert "llm_value_not_in_source:min" in hall["flags"]      # 1.6 不在原文 → 抓到幻覺


def test_llm_missing_rows_reported(cfg):
    client = FakeLLMClient(['{"parameters": [], "ignored_rows": []}'] * 3)
    t = _table()
    _, mapping = llm_extract(t, client, "{{TABLE_MARKDOWN}}", cfg)
    assert all(v == "unmapped:llm_missing" for v in mapping.values())
    assert coverage_of(t, mapping)["coverage"] == 0.0


def test_extract_all_routes_unrecognized_table(cfg):
    from datasheet_extractor.stage3_extract import extract_all
    t = dict(_table(), extract=True)
    res = extract_all([t], cfg, llm_client=None)
    assert res["parameters"] == [] and res["llm_pending"][0]["table_id"] == "T9"
    assert "T9.R1" in res["llm_pending"][0]["prompt_preview"]

    cfg["llm"]["enabled"] = True
    resp = {"parameters": [{"row_id": "T9.R0", "symbol": "fC", "max": "104", "unit": "MHz"},
                           {"row_id": "T9.R1", "symbol": "tCLQX", "min": "1.5", "unit": "ns"}],
            "ignored_rows": [{"row_id": "T9.R2", "reason": "free text"}]}
    res = extract_all([dict(_table(), extract=True)], cfg, llm_client=FakeLLMClient([json.dumps(resp)]))
    assert [p["symbol"] for p in res["parameters"]] == ["fC", "tCLQX"]
    assert res["coverage"][0]["coverage"] == 1.0 and not res["llm_pending"]
    assert res["parameters"][1]["min"]["value_si"] == 1.5e-9
