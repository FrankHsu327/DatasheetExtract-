"""Stage 3b — 逐表抽取 + 覆蓋率追蹤。

核心原則：
- 不再把整份文件丟給 LLM。每次只處理「一張表」，每一列都有 row_id。
- 每一列最後一定落在以下其中一種狀態，否則就是 coverage 缺口：
    parameter | section | repeated_header | empty | ignored:<reason> | unmapped:<reason>
- 規則抽取（rule）優先；規則無法完整覆蓋的表才走 LLM。
- LLM 回傳的數值必須能在該列原文中找到（anti-hallucination），否則加 flag。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .stage2_tables import table_to_markdown
from .text_normalize import normalize_symbol, normalize_text, parse_range, parse_value, split_footnotes

VALUE_ROLES = ("min", "typ", "max", "value")


def _role_map(table: dict) -> dict[str, int]:
    return {c["role"]: c["index"] for c in table["columns"]}


def rule_capable(table: dict) -> bool:
    roles = {c["role"].split("_")[0] for c in table["columns"]}
    return bool(roles & set(VALUE_ROLES)) and bool(roles & {"parameter", "symbol"})


def _notes_for(ids: list[str], table: dict) -> list[dict]:
    out, seen = [], set()
    for i in ids:
        if i in seen:
            continue
        seen.add(i)
        out.append({"id": i, "text": table["footnotes"].get(i)})
    return out


def _source(table: dict, row: dict) -> dict:
    return {"table_id": table["id"], "row_id": row["row_id"], "source_ref": row["source_ref"],
            "source_row": row["source_row"], "pages": table.get("pages", []), "caption": table.get("caption")}


def build_parameter(table: dict, row: dict, fields: dict[str, str | None], method: str) -> dict[str, Any]:
    """fields: name/symbol/conditions/unit/min/typ/max/value (raw strings)."""
    note_ids: list[str] = []
    name_raw = normalize_text(fields.get("name") or "")
    name, n1 = split_footnotes(name_raw)
    symbol_raw = fields.get("symbol") or ""
    symbol = normalize_symbol(symbol_raw) or None
    _, n2 = split_footnotes(normalize_text(symbol_raw))
    note_ids += n1 + n2
    unit = normalize_text(fields.get("unit") or "") or None
    if unit:
        unit, n3 = split_footnotes(unit)
        note_ids += n3
    conditions = normalize_text(fields.get("conditions") or "") or None
    if conditions:
        conditions, n4 = split_footnotes(conditions)
        note_ids += n4
    param: dict[str, Any] = {
        "id": row["row_id"],
        "category": table.get("category"),
        "name": name or None,
        "symbol": symbol,
        "conditions": conditions,
        "alt_symbol": normalize_symbol(fields.get("alt_symbol") or "") or None,
        "section": row.get("section"),
        "unit": unit,
        "min": None, "typ": None, "max": None, "value": None,
        "extra_values": {},
        "notes": [],
        "source": _source(table, row),
        "method": method,
        "flags": [],
    }
    rng = parse_range(fields.get("value"))
    if rng and not fields.get("min") and not fields.get("max"):
        # Absolute max 常見「-0.5 to 4.0」→ 拆成 min / max，原字串保留在 value.raw
        fields = dict(fields, min=rng[0], max=rng[1])
        unit = unit or rng[2]
        param["unit"] = unit
        param["flags"].append("range_split_from_value")
    for k in VALUE_ROLES:
        v = parse_value(fields.get(k), unit)
        param[k] = v
        if v:
            note_ids += v["notes"]
    for header, raw in (fields.get("extra") or {}).items():
        v = parse_value(raw, unit)
        if v:
            param["extra_values"][header] = v
            note_ids += v["notes"]
    param["notes"] = _notes_for(note_ids, table)
    if any(n["text"] is None for n in param["notes"]):
        param["flags"].append("footnote_text_not_found")
    if row.get("filled"):
        param["flags"].append("filled_down_from_merged_cell")
    return param


# ------------------------------------------------------------------ rules
def rule_extract(table: dict) -> tuple[list[dict], dict[str, str]]:
    rm = _role_map(table)
    params: list[dict] = []
    mapping: dict[str, str] = {}
    extra_cols = [c for c in table["columns"]
                  if c["role"] == "other" or re.match(r"^(min|typ|max|value)_\d+$", c["role"])]
    rm.pop("notes", None)
    for row in table["rows"]:
        rid = row["row_id"]
        if row["kind"] in ("section", "repeated_header", "empty"):
            mapping[rid] = row["kind"]
            continue
        cells = row["cells"]

        def get(role: str) -> str | None:
            i = rm.get(role)
            return cells[i] if i is not None and i < len(cells) else None

        fields = {k: get(k) for k in ("parameter", "symbol", "alt_symbol", "conditions", "unit", *VALUE_ROLES)}
        fields["name"] = fields.pop("parameter")
        # 一個值橫跨 MIN/MAX 多欄（合併儲存格）→ 視為單一 value，不要複製到 min 和 max
        origins = row.get("origin_cols") or []
        span_cols = [rm[k] for k in ("min", "typ", "max") if k in rm]
        if origins and span_cols and fields.get("value") is None:
            groups: dict[int, list[str]] = {}
            for k in ("min", "typ", "max"):
                i = rm.get(k)
                if i is not None and i < len(origins) and cells[i]:
                    groups.setdefault(origins[i], []).append(k)
            for keys in groups.values():
                if len(keys) > 1:
                    fields["value"] = fields[keys[0]]
                    for k in keys:
                        fields[k] = None
        if not fields["unit"]:
            for role in VALUE_ROLES:
                i = rm.get(role)
                if i is not None and table["columns"][i]["unit_hint"]:
                    fields["unit"] = table["columns"][i]["unit_hint"]
                    break
        fields["extra"] = {c["header"] or f"col{c['index']}": cells[c["index"]]
                           for c in extra_cols if c["index"] < len(cells) and cells[c["index"]]}
        has_value = any(fields.get(k) for k in VALUE_ROLES)
        has_name = bool(fields["name"] or fields["symbol"])
        if has_value and has_name:
            p = build_parameter(table, row, fields, "rule")
            if all(p[k] is None for k in VALUE_ROLES):
                mapping[rid] = "unmapped:values_unparseable"
                continue
            if fields["extra"]:
                p["flags"].append("has_unrecognized_columns")
            params.append(p)
            mapping[rid] = "parameter"
        elif has_value:
            mapping[rid] = "unmapped:no_name_or_symbol"
        elif has_name:
            mapping[rid] = "unmapped:no_values"
        else:
            mapping[rid] = "unmapped:unrecognized_layout"
    return params, mapping


# -------------------------------------------------------------------- LLM
def build_llm_prompt(table: dict, template: str, only_rows: list[str] | None = None) -> str:
    md = table_to_markdown(table)
    if only_rows:
        keep = set(only_rows)
        lines = md.split("\n")
        md = "\n".join(lines[:2] + [ln for ln in lines[2:] if ln.split("|")[1].strip() in keep])
    notes = "\n".join(f"({k}) {v}" for k, v in table["footnotes"].items()) or "(none)"
    return (template
            .replace("{{CAPTION}}", table.get("caption") or "(no caption)")
            .replace("{{SECTION}}", " > ".join(table.get("section_path", [])) or "(unknown)")
            .replace("{{CATEGORY}}", str(table.get("category")))
            .replace("{{TABLE_MARKDOWN}}", md)
            .replace("{{FOOTNOTES}}", notes)
            .replace("{{ROW_IDS}}", ", ".join(only_rows) if only_rows else "ALL rows listed in the table"))


def _parse_llm_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    data = json.loads(text)
    if isinstance(data, list):
        data = {"parameters": data, "ignored_rows": []}
    return data


def _value_in_row(raw: str | None, row: dict) -> bool:
    if not raw:
        return True
    needle = normalize_text(raw).replace(" ", "").lower()
    hay = "".join(row["cells"]).replace(" ", "").lower()
    return needle in hay


def llm_extract(table: dict, client, template: str, cfg: dict) -> tuple[list[dict], dict[str, str]]:
    """LLM 逐表抽取 + 強制覆蓋率。client 需實作 complete(system, user) -> str（見 llm_client.py）。"""
    rows_by_id = {r["row_id"]: r for r in table["rows"]}
    mapping: dict[str, str] = {r["row_id"]: r["kind"] for r in table["rows"]
                               if r["kind"] in ("section", "repeated_header", "empty")}
    pending = [rid for rid in rows_by_id if rid not in mapping]
    params: list[dict] = []
    attempts = 1 + int(cfg["llm"].get("max_retries_for_missing_rows", 1))
    system = "You extract electrical specification rows from datasheet tables into strict JSON. Never invent values."

    for attempt in range(attempts):
        if not pending:
            break
        prompt = build_llm_prompt(table, template, only_rows=pending if attempt > 0 else None)
        try:
            data = _parse_llm_json(client.complete(system=system, user=prompt))
        except NotImplementedError:
            raise
        except Exception as e:  # noqa: BLE001 - 回應格式錯誤時不中斷整份文件
            table["flags"].append(f"llm_error:{type(e).__name__}")
            break
        for entry in data.get("parameters", []):
            rid = entry.get("row_id")
            if rid not in rows_by_id or rid not in pending:
                continue
            row = rows_by_id[rid]
            fields = {k: entry.get(k) for k in ("name", "symbol", "conditions", "unit", *VALUE_ROLES)}
            p = build_parameter(table, row, fields, "llm")
            for k in ("name", "symbol", *VALUE_ROLES):
                if not _value_in_row(fields.get(k), row):
                    p["flags"].append(f"llm_value_not_in_source:{k}")
            params.append(p)
            mapping[rid] = "parameter"
        for ig in data.get("ignored_rows", []):
            rid = ig.get("row_id")
            if rid in rows_by_id and rid in pending and rid not in mapping:
                mapping[rid] = f"ignored:{ig.get('reason', 'llm')}"
        pending = [rid for rid in pending if rid not in mapping]

    for rid in pending:
        mapping[rid] = "unmapped:llm_missing"
    return params, mapping


# ---------------------------------------------------------------- driver
def coverage_of(table: dict, mapping: dict[str, str]) -> dict[str, Any]:
    rows = [r for r in table["rows"] if r["kind"] != "empty"]
    status_count: dict[str, int] = {}
    for r in rows:
        s = mapping.get(r["row_id"], "unmapped:not_processed").split(":")[0]
        status_count[s] = status_count.get(s, 0) + 1
    unmapped = [{"row_id": r["row_id"], "status": mapping.get(r["row_id"], "unmapped:not_processed"),
                 "cells": r["cells"]} for r in rows
                if mapping.get(r["row_id"], "unmapped").startswith("unmapped")]
    total = len(rows)
    accounted = total - len(unmapped)
    return {"table_id": table["id"], "caption": table.get("caption"), "category": table.get("category"),
            "rows_total": total, "rows_accounted": accounted,
            "coverage": round(accounted / total, 4) if total else 1.0,
            "status_count": status_count, "unmapped_rows": unmapped}


def extract_all(tables: list[dict], cfg: dict, llm_client=None) -> dict[str, Any]:
    template = ""
    tpl_path = Path(__file__).resolve().parent.parent / cfg["llm"]["prompt_file"]
    if tpl_path.exists():
        template = tpl_path.read_text(encoding="utf-8")
    all_params: list[dict] = []
    coverage: list[dict] = []
    llm_pending: list[dict] = []
    min_cov = float(cfg["extract"].get("min_rule_coverage", 1.0))

    for t in tables:
        if not t.get("extract"):
            continue
        params, mapping, method = [], {}, None
        if cfg["extract"].get("use_rules_first", True) and rule_capable(t):
            params, mapping = rule_extract(t)
            method = "rule"
            cov = coverage_of(t, mapping)
            if cov["coverage"] < min_cov:
                t["flags"].append(f"rule_coverage_below_threshold:{cov['coverage']}")
                method = "rule+needs_llm"
        else:
            method = "needs_llm"

        if method in ("needs_llm", "rule+needs_llm"):
            if cfg["llm"].get("enabled") and llm_client is not None:
                if method == "rule+needs_llm":
                    # 只把規則沒處理好的列交給 LLM，其餘保留規則結果
                    unmapped = {rid for rid, s in mapping.items() if s.startswith("unmapped")}
                    sub = dict(t, rows=[r for r in t["rows"] if r["row_id"] in unmapped])
                    p2, m2 = llm_extract(sub, llm_client, template, cfg)
                    params += p2
                    mapping.update(m2)
                else:
                    params, mapping = llm_extract(t, llm_client, template, cfg)
                method = method.replace("needs_llm", "llm")
            else:
                llm_pending.append({"table_id": t["id"], "caption": t.get("caption"),
                                    "category": t.get("category"),
                                    "prompt_preview": build_llm_prompt(t, template)[:4000] if template else None})
        t["extraction_method"] = method
        all_params.extend(params)
        coverage.append(coverage_of(t, mapping))
    return {"parameters": all_params, "coverage": coverage, "llm_pending": llm_pending}
