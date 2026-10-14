"""Golden set 評估 + 遺漏歸因（回答「到底漏在哪一層」）。

golden 檔格式（golden/<stem>.golden.json）：
{
  "datasheet": "W25Q32JV.pdf",
  "parameters": [
    {"symbol": "VIH", "conditions": null, "min": "0.7 x VCC", "typ": null, "max": "VCC+0.4", "unit": "V"},
    {"symbol": "tCLQV", "conditions": "CL = 30pF", "max": "6", "unit": "ns"}
  ]
}

每個 golden 參數會被歸因到：
  ok                       抽取正確
  value_mismatch           找到了但數值不同（TableFormer 錯格 / 註腳黏數字 / LLM 改寫）
  lost_in_extraction       Docling 表格內有這列，但 Stage 3 沒產出參數（規則/LLM 漏列）
  lost_in_docling          Docling 任何表格內都找不到（Layout 沒偵測到表、TableFormer 漏格、表格是圖片）
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .docling_reader import DoclingDoc, table_grid
from .text_normalize import normalize_symbol, normalize_text, numeric_tokens, parse_value

VALUE_KEYS = ("min", "typ", "max", "value")


def _same_value(golden_raw: str | None, got: dict | None, unit: str | None, rel_tol: float = 1e-6) -> bool:
    g = parse_value(golden_raw, unit) if golden_raw is not None else None
    if g is None:
        return got is None or (got.get("value") is None and not got.get("expr"))
    if got is None:
        return False
    if g.get("value_si") is not None and got.get("value_si") is not None:
        a, b = g["value_si"], got["value_si"]
        return abs(a - b) <= rel_tol * max(abs(a), abs(b), 1e-30)
    if g.get("value") is not None and got.get("value") is not None:
        return abs(g["value"] - got["value"]) <= rel_tol * max(abs(g["value"]), 1e-30)
    ge = (g.get("expr") or "").replace(" ", "").lower()
    ce = (got.get("expr") or "").replace(" ", "").lower()
    return bool(ge) and ge == ce


def _cond_score(golden_cond: str | None, cand_cond: str | None) -> int:
    if not golden_cond:
        return 0
    gt = set(numeric_tokens(golden_cond))
    ct = set(numeric_tokens(cand_cond or ""))
    return len(gt & ct)


def _raw_rows_with_symbol(doc: DoclingDoc, symbol: str) -> list[list[str]]:
    target = normalize_symbol(symbol).lower()
    rows = []
    for t in doc.data.get("tables", []):
        grid, _ = table_grid(t)
        for row in grid:
            if any(normalize_symbol(c).lower() == target for c in row):
                rows.append([normalize_text(c) for c in row])
    return rows


_THOUSANDS_RE = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")


def _row_tokens(row: list[str]) -> tuple[set[str], set[str]]:
    """(symbol-like words, numeric tokens) of one table row; spanned cells are deduplicated."""
    words: set[str] = set()
    nums: set[str] = set()
    for cell in dict.fromkeys(row):
        text = _THOUSANDS_RE.sub("", normalize_text(cell))   # 1,600 → 1600
        nums.update(t.lstrip("-") for t in numeric_tokens(text))
        words.add(normalize_symbol(text).lower())          # 整格：VUVLO,rise、RPU,RPD、|IIn|
        for part in text.replace(",", " ").split():
            words.add(normalize_symbol(part).lower())
    return words, nums


def stage1_fidelity(golden: dict, docling_doc: DoclingDoc) -> dict[str, Any]:
    """Stage 1 判定（不依賴 Stage 2–4 規則）：golden 參數的 symbol 與所有數值是否同時出現在某張表的同一列。

    ok        某列同時含 symbol、全部 golden 數值、以及 conditions 中的數字
    partial   有含 symbol 的列，但數值不全（漏格、錯格、數值被併進別格後被拆錯）
    missing   沒有任何列含此 symbol（表沒偵測到、整列遺失、symbol 被併進別的字）
    """
    rows = []
    for t in docling_doc.data.get("tables", []):
        grid, _ = table_grid(t)
        rows.extend(_row_tokens(r) for r in grid)
    results, counts = [], {"ok": 0, "partial": 0, "missing": 0}
    for g in golden.get("parameters", []):
        sym = normalize_symbol(g["symbol"]).lower()
        want = {t.lstrip("-") for k in VALUE_KEYS if g.get(k) for t in numeric_tokens(str(g[k]))}
        want |= {t.lstrip("-") for t in numeric_tokens(g.get("conditions") or "")}
        with_sym = [nums for words, nums in rows if sym in words]
        if not with_sym:
            status = "missing"
        elif any(want <= nums for nums in with_sym):
            status = "ok"
        else:
            status = "partial"
        counts[status] += 1
        results.append({"symbol": g["symbol"], "conditions": g.get("conditions"), "status": status})
    n = len(results)
    return {"fidelity": round(counts["ok"] / n, 4) if n else None, "status_count": counts, "details": results}


_FIG_LABEL_RE = re.compile(r"fig(?:ure)?\.?\s*(\d+[a-z]?(?:-\d+[a-z]?)?)", re.I)


def figure_eval(golden: dict, docling_doc: DoclingDoc) -> dict[str, Any] | None:
    """golden["figures"]（page + "Figure N"）對方法輸出的 pictures。

    found     同一頁有 picture，且 caption 含相同圖號；沒有的話，同一頁有尚未配對、沒有 caption 的 picture 也算
    described 配對到的 picture 帶有後端內建的描述（Docling picture description / hybrid 的 Granite Vision）
    """
    from .figures import picture_class, picture_description

    gold = golden.get("figures") or []
    if not gold:
        return None
    pics = []
    for i, p in enumerate(docling_doc.data.get("pictures", [])):
        prov = docling_doc.provenance(p)
        pics.append({"i": i, "page": prov[0]["page"] if prov else None,
                     "labels": {m.lower() for m in _FIG_LABEL_RE.findall(docling_doc.caption_text(p))},
                     "desc": picture_description(p), "cls": picture_class(p)})
    used: set[int] = set()
    details = []
    for g in gold:
        num = g["label"].split()[-1].lower()
        hit = next((p for p in pics if p["i"] not in used and p["page"] == g["page"] and num in p["labels"]), None)
        how = "caption"
        if hit is None:
            hit = next((p for p in pics if p["i"] not in used and p["page"] == g["page"] and not p["labels"]), None)
            how = "same_page"
        if hit is not None:
            used.add(hit["i"])
        details.append({"page": g["page"], "label": g["label"], "found": hit is not None,
                        "match": how if hit else None, "picture": f"#/pictures/{hit['i']}" if hit else None,
                        "described": bool(hit and hit["desc"]), "class": hit["cls"] if hit else None})
    n = len(details)
    found = sum(d["found"] for d in details)
    described = sum(d["described"] for d in details)
    return {"golden_count": n, "found": found, "recall": round(found / n, 4),
            "described": described, "described_ratio": round(described / n, 4),
            "pictures_total": len(pics), "pictures_unmatched": len(pics) - len(used), "details": details}


def evaluate(component: dict, golden: dict, docling_doc: DoclingDoc | None = None) -> dict[str, Any]:
    params = component["parameters"]
    results = []
    for g in golden.get("parameters", []):
        sym = normalize_symbol(g["symbol"]).lower()
        from .stage4_validate import symbol_variants
        cands = [p for p in params if sym in {s.lower() for s in symbol_variants(p)}]
        best, best_score = None, -1
        for c in cands:
            matches = sum(_same_value(g.get(k), c.get(k), g.get("unit")) for k in VALUE_KEYS if k in g)
            score = matches * 10 + _cond_score(g.get("conditions"), c.get("conditions"))
            if score > best_score:
                best, best_score = c, score
        status = "ok"
        detail: dict[str, Any] = {}
        if best is not None:
            bad = [k for k in VALUE_KEYS if k in g and not _same_value(g.get(k), best.get(k), g.get("unit"))]
            if bad:
                status = "value_mismatch"
                detail = {k: {"golden": g.get(k), "got": (best.get(k) or {}).get("raw")} for k in bad}
        else:
            in_docling = bool(docling_doc and _raw_rows_with_symbol(docling_doc, g["symbol"]))
            status = "lost_in_extraction" if in_docling else ("lost_in_docling" if docling_doc else "missing")
        results.append({"symbol": g["symbol"], "conditions": g.get("conditions"), "status": status,
                        "matched_id": best["id"] if best else None, "detail": detail})

    n = len(results)
    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    golden_syms = {normalize_symbol(g["symbol"]).lower() for g in golden.get("parameters", [])}
    extra = [p["id"] for p in params if p.get("symbol") and p["symbol"].lower() not in golden_syms]
    return {
        "golden_count": n,
        "recall": round(counts.get("ok", 0) / n, 4) if n else None,
        "found_ratio": round((n - counts.get("lost_in_docling", 0) - counts.get("lost_in_extraction", 0)
                              - counts.get("missing", 0)) / n, 4) if n else None,
        "status_count": counts,
        "loss_attribution": {k: v for k, v in counts.items() if k != "ok"},
        "extracted_not_in_golden": extra,
        "details": results,
        "stage1": stage1_fidelity(golden, docling_doc) if docling_doc else None,
        "figures": figure_eval(golden, docling_doc) if docling_doc else None,
    }


def evaluate_files(component_json: str | Path, golden_json: str | Path, docling_json: str | Path | None = None) -> dict:
    comp = json.loads(Path(component_json).read_text(encoding="utf-8"))
    gold = json.loads(Path(golden_json).read_text(encoding="utf-8"))
    doc = DoclingDoc.load(docling_json) if docling_json else None
    return evaluate(comp, gold, doc)
