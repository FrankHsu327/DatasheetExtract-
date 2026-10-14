"""CLI.

  python -m datasheet_extractor run <pdf|dir> --out out/
  python -m datasheet_extractor view <pdf> --golden golden/X.golden.json [--reuse]   → out/review/<stem>/compare.html
  python -m datasheet_extractor summary [--out out/review]
  python -m datasheet_extractor run-json out/X/01_docling/document.json --pdf X.pdf --component spi_rom --out out/X
  python -m datasheet_extractor diagnose out/X/01_docling/document.json [--pdf X.pdf]
  python -m datasheet_extractor evaluate out/X/X.component.json golden/X.golden.json [--docling-json ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_config


def _summary(comp: dict) -> str:
    q = comp["quality"]
    v = q["validation"]
    lines = [
        f"file: {comp['datasheet']['file']}",
        f"parts: {', '.join(comp['component']['part_numbers']) or '-'}",
        f"parameters: {v['parameter_count']} (flagged {v['flagged_parameters']})",
        "coverage: " + ", ".join(f"{c['table_id']}={c['coverage']}" for c in q["coverage"]),
        f"expected missing: {', '.join(v['expected']['missing']) or 'none'}",
        f"llm pending tables: {len(q['llm_pending'])}",
        f"needs_review: {q['needs_review']}",
    ]
    if q.get("crosscheck"):
        lines.append("crosscheck recall: " + ", ".join(f"{c['table_id']}={c['token_recall']}" for c in q["crosscheck"]))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="datasheet_extractor")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="PDF → component JSON (Stage 1 hybrid + Stage 2–4)")
    r.add_argument("source", help="PDF file or directory of PDFs")
    r.add_argument("--component", default="generic")
    r.add_argument("--out", default="out")
    r.add_argument("--config", help="extra yaml to override")

    v = sub.add_parser("view", help="Run hybrid on one PDF, score with golden, build compare.html (output vs PDF)")
    v.add_argument("pdf")
    v.add_argument("--component", default="generic")
    v.add_argument("--golden", help="golden.json for scoring")
    v.add_argument("--out", default="out/review")
    v.add_argument("--reuse", action="store_true", help="reuse existing Stage 1 output (Stage 2-4 always rerun)")

    s = sub.add_parser("summary", help="Cross-datasheet summary: <out>/index.html + summary.md")
    s.add_argument("--out", default="out/review")

    rj = sub.add_parser("run-json", help="Run stage 2+ from an existing Docling JSON (no docling needed)")
    rj.add_argument("docling_json")
    rj.add_argument("--pdf", help="original PDF for crosscheck")
    rj.add_argument("--component", default="spi_rom")
    rj.add_argument("--out", required=True)
    rj.add_argument("--config")

    d = sub.add_parser("diagnose", help="Find suspected losses in Docling output")
    d.add_argument("docling_json")
    d.add_argument("--pdf")
    d.add_argument("--component", default="spi_rom")

    e = sub.add_parser("evaluate", help="Compare component JSON with golden set")
    e.add_argument("component_json")
    e.add_argument("golden_json")
    e.add_argument("--docling-json")

    a = ap.parse_args(argv)
    from .model_env import setup as _model_env
    _model_env()

    if a.cmd == "run":
        from .pipeline import run
        cfg = load_config(a.component, a.config)
        src = Path(a.source)
        files = sorted(src.glob("*.pdf")) if src.is_dir() else [src]
        rc = 0
        for f in files:
            try:
                comp = run(f, a.out, cfg)
                print(_summary(comp), end="\n\n")
            except Exception as ex:  # noqa: BLE001
                rc = 1
                print(f"[FAIL] {f}: {ex}", file=sys.stderr)
        return rc

    if a.cmd == "view":
        from .view import view
        html = view(Path(a.pdf), Path(a.out), a.component, a.golden, a.reuse)
        print(f"compare view: {html}")
        return 0

    if a.cmd == "summary":
        from .summary import write
        print(f"summary: {write(Path(a.out))}")
        return 0

    if a.cmd == "run-json":
        from .pipeline import run_from_docling_json
        cfg = load_config(a.component, a.config)
        comp = run_from_docling_json(a.docling_json, a.out, cfg, pdf_path=a.pdf,
                                     source_name=Path(a.pdf).name if a.pdf else None)
        print(_summary(comp))
        return 0

    if a.cmd == "diagnose":
        from .diagnose import diagnose
        from .docling_reader import DoclingDoc
        from .stage2_tables import extract_tables
        from .stage3_locate import locate
        cfg = load_config(a.component)
        doc = DoclingDoc.load(a.docling_json)
        tables, _ = extract_tables(doc, cfg)
        locate(tables, cfg)
        print(json.dumps(diagnose(doc, a.pdf, tables), ensure_ascii=False, indent=2))
        return 0

    if a.cmd == "evaluate":
        from .evaluate import evaluate_files
        res = evaluate_files(a.component_json, a.golden_json, a.docling_json)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
