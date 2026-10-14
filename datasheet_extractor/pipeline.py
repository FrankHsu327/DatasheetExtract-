"""Pipeline orchestration. 每個 stage 的中間結果都落地，方便逐層診斷遺漏。

out/<stem>/
  01_docling/        Stage 1（document.json / .md / pages / tables / figures / meta.json）
  02_tables/         tables.json, merge_log.json
  03_extract/        parameters.json, coverage.json, llm_pending.json
  04_validate/       validation.json, crosscheck.json, schema_errors.json
  diagnose.json
  <stem>.component.json   ← 最終產物（一個元件一個 JSON）
  review.html
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from . import __version__
from .docling_reader import DoclingDoc
from .figures import collect_figures, describe_figures, link_figures_to_parameters
from .llm_client import get_client
from .stage2_tables import extract_tables
from .stage3_extract import extract_all
from .stage3_locate import locate
from .stage4_validate import validate, validate_schema
from .review import INFO_FLAGS, render
from .diagnose import diagnose


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _find_part_numbers(doc: DoclingDoc, cfg: dict, limit_texts: int = 80) -> list[str]:
    pats = [re.compile(p) for p in cfg.get("component", {}).get("part_number_patterns", [])]
    found: list[str] = []
    for i, t in enumerate(doc.data.get("texts", [])):
        if i > limit_texts:
            break
        for p in pats:
            for m in p.findall(t.get("text", "")):
                if m not in found:
                    found.append(m)
    return found


def _title(doc: DoclingDoc) -> str | None:
    for t in doc.data.get("texts", [])[:30]:
        if t.get("label") in ("title", "section_header") and t.get("text"):
            return t["text"]
    return None


def run_from_docling_json(docling_json: str | Path, out_dir: str | Path, cfg: dict,
                          pdf_path: str | Path | None = None, source_name: str | None = None,
                          llm_client=None) -> dict[str, Any]:
    out = Path(out_dir)
    doc = DoclingDoc.load(docling_json)
    stem = Path(source_name or doc.name).stem

    # Stage 2
    tables, merge_log = extract_tables(doc, cfg)
    # Stage 3a
    locate(tables, cfg)
    _write(out / "02_tables" / "tables.json", tables)
    _write(out / "02_tables" / "merge_log.json", merge_log)

    # Stage 3b
    client = llm_client if llm_client is not None else get_client(cfg)
    ext = extract_all(tables, cfg, client)
    params = ext["parameters"]
    _write(out / "03_extract" / "parameters.json", params)
    _write(out / "03_extract" / "coverage.json", ext["coverage"])
    _write(out / "03_extract" / "llm_pending.json", ext["llm_pending"])

    # Figures
    figures = collect_figures(doc, cfg, out / "01_docling" / "figures")
    describe_figures(figures, cfg)
    link_figures_to_parameters(figures, params)

    # Stage 4
    validation = validate(params, ext["coverage"], cfg)
    crosscheck = None
    if pdf_path and cfg["crosscheck"].get("enabled", True):
        from .crosscheck import crosscheck_tables
        crosscheck = crosscheck_tables(pdf_path, tables, cfg)
        _write(out / "04_validate" / "crosscheck.json", crosscheck)
    _write(out / "04_validate" / "validation.json", validation)

    meta_path = out / "01_docling" / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    needs_review = bool(
        any(f.split(":")[0] not in INFO_FLAGS for p in params for f in p["flags"])
        or validation["tables_with_incomplete_coverage"] or validation["expected"]["missing"]
        or ext["llm_pending"] or any(not c["pass"] for c in (crosscheck or []))
        or any(f.get("needs_review") for f in figures))

    component = {
        "schema_version": "0.1.0",
        "component": {"category": cfg["component"]["name"], "part_numbers": _find_part_numbers(doc, cfg),
                      "manufacturer": None},
        "datasheet": {"file": meta.get("source_file") or source_name or doc.name,
                      "sha256": meta.get("source_sha256") or doc.origin_hash and str(doc.origin_hash),
                      "title": _title(doc), "revision": None, "pages": len(doc.data.get("pages", {})) or None},
        "extraction": {"timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                       "tool_version": __version__, "docling_version": meta.get("docling_version"),
                       "config_hash": hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()[:16],
                       "llm_used": any(p["method"] == "llm" for p in params)},
        "parameters": params,
        "tables": [_public_table(t) for t in tables],
        "figures": figures,
        "quality": {"coverage": ext["coverage"], "crosscheck": crosscheck, "validation": validation,
                    "expected_parameters": validation["expected"], "llm_pending": ext["llm_pending"],
                    "needs_review": needs_review},
    }
    schema_errors = validate_schema(component)
    _write(out / "04_validate" / "schema_errors.json", schema_errors)
    component["quality"]["validation"]["schema_errors"] = len(schema_errors)

    _write(out / "diagnose.json", diagnose(doc, pdf_path, tables))
    _write(out / f"{stem}.component.json", component)
    render(component, out)
    return component


def _public_table(t: dict) -> dict:
    keep = ("id", "caption", "category", "pages", "section_path", "columns", "header_texts", "footnotes",
            "provenance", "source_refs", "flags", "merge_log", "spec_like", "extraction_method")
    out = {k: t.get(k) for k in keep}
    out["rows"] = [{"row_id": r["row_id"], "kind": r["kind"], "section": r["section"], "cells": r["cells"]}
                   for r in t["rows"] if r["kind"] != "empty"]
    return out


def run_stage1(source: Path, out: Path, cfg: dict) -> Path:
    """Stage 1（hybrid）→ <out>/01_docling/document.json（DoclingDocument 格式）。"""
    from .stage1_hybrid import convert_hybrid
    return convert_hybrid(source, out, cfg)


def run(source: str | Path, out_root: str | Path, cfg: dict, llm_client=None) -> dict[str, Any]:
    """Full pipeline from a PDF：Stage 1（hybrid）→ Stage 2–4。"""
    source = Path(source)
    out = Path(out_root) / source.stem
    docling_json = run_stage1(source, out, cfg)
    pdf = source if source.suffix.lower() == ".pdf" else None
    return run_from_docling_json(docling_json, out, cfg, pdf_path=pdf, source_name=source.name,
                                 llm_client=llm_client)
