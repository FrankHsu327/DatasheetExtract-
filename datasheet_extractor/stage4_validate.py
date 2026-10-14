"""Stage 4 — 驗證：schema、物理合理性、覆蓋率、關鍵參數清單、衝突值。

所有檢查結果都會寫回 parameter.flags，並匯總到 quality.validation。
任何 flag 都代表「需要人看」，而不是自動丟棄資料。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "component.schema.json"

_UNIT_EXPECT = [  # (symbol regex, expected si_unit, label)
    (re.compile(r"^v", re.I), "V", "voltage"),
    (re.compile(r"^i", re.I), "A", "current"),
    (re.compile(r"^t(?!emp|a$|j$|stg$|op)", re.I), "s", "time"),
    (re.compile(r"^f", re.I), "Hz", "frequency"),
    (re.compile(r"^c(in|out|io|i|o)?$", re.I), "F", "capacitance"),
]


def _si(v: dict | None) -> float | None:
    return v.get("value_si") if v else None


def sanity_check(p: dict) -> list[str]:
    flags = []
    mn, ty, mx = _si(p["min"]), _si(p["typ"]), _si(p["max"])
    if mn is not None and mx is not None and mn > mx:
        flags.append("min_gt_max")
    if mn is not None and ty is not None and mn > ty:
        flags.append("min_gt_typ")
    if ty is not None and mx is not None and ty > mx:
        flags.append("typ_gt_max")
    vals = (p["min"], p["typ"], p["max"]) + (() if "range_split_from_value" in p["flags"] else (p["value"],))
    units = {v["si_unit"] for v in vals if v and v.get("si_unit")}
    if len(units) > 1:
        flags.append("mixed_units:" + ",".join(sorted(units)))
    has_numeric = any(v and v.get("value") is not None for v in vals)
    has_expr = any(v and v.get("expr") for v in vals)
    if has_numeric and not units and not p.get("unit"):
        flags.append("missing_unit")
    elif has_numeric and p.get("unit") and not units:
        flags.append(f"unknown_unit:{p['unit']}")
    if has_expr:
        flags.append("expression_value")
    sym = p.get("symbol") or ""
    if sym and units and not units <= {"°C"}:      # T 開頭但單位是 °C → 溫度參數，不做 time 檢查
        for rx, expected, label in _UNIT_EXPECT:
            if rx.match(sym):
                if expected not in units and not ({"cycles"} & units):
                    flags.append(f"unit_mismatch_for_{label}:{','.join(sorted(units))}")
                break
    is_esd = "esd" in (sym + " " + (p.get("name") or "")).lower()
    for v in (p["min"], p["typ"], p["max"], p["value"]):
        if is_esd:
            break
        if v and v.get("value_si") is not None and v.get("si_unit") == "V" and abs(v["value_si"]) > 60:
            flags.append("implausible_voltage")
    return flags


def find_conflicts(params: list[dict]) -> list[dict]:
    """同 symbol + 同 conditions 卻有不同數值 → 可能是多料號/多電壓版本沒分開，或抽取錯誤。"""
    seen: dict[tuple, dict] = {}
    conflicts = []
    for p in params:
        if not p.get("symbol"):
            continue
        # 名稱也納入 key：同 symbol 但名稱不同（例：ICC3 @50/80/104MHz）是不同規格，不是衝突
        key = (p["category"], p["symbol"].lower(), (p.get("name") or "").lower(),
               (p.get("conditions") or "").lower(), (p.get("section") or "").lower())
        vals = tuple(_si(p[k]) for k in ("min", "typ", "max", "value"))
        if key in seen and seen[key]["vals"] != vals:
            conflicts.append({"symbol": p["symbol"], "a": seen[key]["id"], "b": p["id"]})
            p["flags"].append(f"conflict_with:{seen[key]['id']}")
        else:
            seen.setdefault(key, {"id": p["id"], "vals": vals})
    return conflicts


def symbol_variants(p: dict) -> list[str]:
    """'tCLH,tCLL' → ['tCLH,tCLL','tCLH','tCLL'] + alt_symbol（例：tCSS）"""
    out = []
    for s in (p.get("symbol"), p.get("alt_symbol")):
        if not s:
            continue
        s = s.replace(" ", "")
        out.append(s)
        out.extend(x for x in re.split(r"[,/]", s) if x and x != s)
    return out


def check_expected(params: list[dict], expected: list[dict]) -> dict[str, Any]:
    found: dict[str, list[str]] = {}
    missing = []
    for e in expected or []:
        rx = re.compile(e["match"], re.I)
        hits = []
        for p in params:
            if e.get("category") and p.get("category") and p["category"] != e["category"] \
                    and not (e["category"] == "recommended_operating" and p["category"] == "absolute_max"):
                continue                            # 只在預期的表格類別中比對，避免名稱關鍵字誤配
            syms = symbol_variants(p)
            name = (p.get("name") or "").lower()
            if any(rx.search(s) for s in syms) or any(k in name for k in e.get("name_any", [])):
                hits.append(p["id"])
        if hits:
            found[e["key"]] = hits
        else:
            missing.append(e["key"])
    total = len(expected or [])
    return {"found": found, "missing": missing,
            "found_ratio": round(len(found) / total, 4) if total else 1.0}


def validate_schema(component: dict) -> list[str]:
    try:
        import jsonschema
    except ImportError:
        return ["jsonschema_not_installed"]
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message}"[:300] for e in validator.iter_errors(component)]


def validate(params: list[dict], coverage: list[dict], cfg: dict) -> dict[str, Any]:
    flag_count: dict[str, int] = {}
    for p in params:
        p["flags"].extend(f for f in sanity_check(p) if f not in p["flags"])
    conflicts = find_conflicts(params)
    for p in params:
        for f in p["flags"]:
            k = f.split(":")[0]
            flag_count[k] = flag_count.get(k, 0) + 1
    low_cov = [c for c in coverage if c["coverage"] < 1.0]
    expected = check_expected(params, cfg.get("expected_parameters", []))
    return {
        "parameter_count": len(params),
        "flagged_parameters": sum(1 for p in params if p["flags"]),
        "flag_count": flag_count,
        "conflicts": conflicts,
        "tables_with_incomplete_coverage": [{"table_id": c["table_id"], "coverage": c["coverage"]} for c in low_cov],
        "expected": expected,
    }
