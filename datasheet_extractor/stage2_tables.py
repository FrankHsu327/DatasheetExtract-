"""Stage 2 — 確定性表格後處理（不使用 LLM）。

輸入：Docling JSON（DoclingDocument.export_to_dict()）
輸出：normalized tables，每一列都有穩定的 row_id，供 Stage 3 做覆蓋率追蹤。

處理項目：
1. grid 重建（含 row/col span）
2. 多層表頭合併：「Limits / Min」→ role=min
3. 欄位角色辨識（parameter / symbol / conditions / min / typ / max / unit / value / notes）
4. section row 辨識（例如整列寫著 "Read Mode" 的分組列）
5. fill-down：合併儲存格造成的空白 parameter / conditions
6. 表格內重複表頭列標記（跨頁表格常見）
7. 跨頁 / 被切斷表格合併（continued、相同 Table N、相同欄數且中間無內文）
8. 表格註腳收集（Note 1: ...）
"""
from __future__ import annotations

import re
from typing import Any

from .docling_reader import DoclingDoc, table_grid
from .text_normalize import normalize_text, unit_from_header, NUM_TOKEN_RE

ROLE_PRIORITY = ["conditions", "alt_symbol", "symbol", "min", "typ", "max", "unit", "parameter", "value", "notes"]
_TABLE_NO_RE = re.compile(r"\btable\s*([0-9]+(?:[-.][0-9]+)?)", re.I)
_NOTE_START_RE = re.compile(r"^\s*(notes?\s*[:.]?|\(\d+\)|\d+\s*[.)]|\*)", re.I)
_NOTE_ITEM_RE = re.compile(r"(?:^|\s)(?:\((\d+)\)|(\d+)[.)])\s+")


# ------------------------------------------------------------------ roles
def detect_role(header: str, keywords: dict[str, list[str]]) -> str | None:
    h = normalize_text(header).lower()
    if not h:
        return None
    segments = [s.strip() for s in h.split(" / ") if s.strip()]
    for text in [segments[-1], h] if segments else [h]:
        text = re.sub(r"[\(\[].*?[\)\]]", " ", text).strip()   # 去掉 (ns) 之類
        for role in ROLE_PRIORITY:
            for kw in keywords.get(role, []):
                if re.search(rf"(^|[^a-z]){re.escape(kw)}s?([^a-z]|$)", text):   # 允許複數 PARAMETERS
                    return role
    return None


def _assign_roles(headers: list[str], keywords: dict) -> list[str]:
    roles: list[str] = []
    used: set[str] = set()
    for h in headers:
        r = detect_role(h, keywords)
        if r and r in used and r not in ("notes",):
            r = f"{r}_{sum(1 for x in roles if x and x.startswith(r))+1}"  # 第二個 max → max_2，保留但不覆蓋
        roles.append(r or "other")
        if r:
            used.add(r)
    return _parameter_is_symbol(headers, roles)


def _parameter_is_symbol(headers: list[str], roles: list[str]) -> list[str]:
    """Infineon/Cypress 慣例：沒有 Symbol 欄、但同時有 Parameter 與 Description 欄時，
    Parameter 欄放的是 symbol（VDDIO_ABS），Description 才是參數名稱；Spec ID 之類的欄位不當名稱。"""
    if any(r == "symbol" for r in roles):
        return roles
    low = [normalize_text(h).lower() for h in headers]
    desc = [i for i, h in enumerate(low) if "description" in h]
    par = [i for i, h in enumerate(low) if re.search(r"\bparameters?\b", h)]
    if not desc or not par or desc[0] == par[0]:
        return roles
    roles = list(roles)
    roles[par[0]], roles[desc[0]] = "symbol", "parameter"
    for i, r in enumerate(roles):
        if i not in (par[0], desc[0]) and r.startswith("parameter"):
            roles[i] = "other"
    return roles


# ------------------------------------------------------------ one table
def _header_row_count(grid: list[list[str]], meta: list[list[dict]], keywords: dict) -> int:
    n = 0
    for r, row in enumerate(grid):
        cells = [(c, meta[r][i]) for i, c in enumerate(row) if c.strip()]
        if cells and all(m["column_header"] for _, m in cells):
            n += 1
        else:
            break
    if n == 0 and grid:
        # Docling 沒標 column_header 時的 fallback：第一列有 ≥2 個表頭關鍵字
        hits = sum(1 for c in grid[0] if detect_role(c, keywords))
        has_numbers = any(NUM_TOKEN_RE.search(c) for c in grid[0])
        if hits >= 2 and not has_numbers:
            n = 1
    return n


def _combine_headers(grid: list[list[str]], n: int) -> list[str]:
    if not grid:
        return []
    ncols = len(grid[0])
    out = []
    for c in range(ncols):
        parts: list[str] = []
        for r in range(n):
            t = normalize_text(grid[r][c])
            if t and (not parts or parts[-1] != t):
                parts.append(t)
        out.append(" / ".join(parts))
    return out


def normalize_table(doc: DoclingDoc, item: dict, table_id: str, cfg: dict) -> dict[str, Any]:
    tcfg = cfg["tables"]
    keywords = tcfg["header_keywords"]
    grid, meta = table_grid(item)
    n_header = _header_row_count(grid, meta, keywords)
    headers = _combine_headers(grid, n_header)
    roles = _assign_roles(headers, keywords)
    columns = [{"index": i, "header": h, "role": roles[i], "unit_hint": unit_from_header(h)}
               for i, h in enumerate(headers)]
    if not headers and grid:
        columns = [{"index": i, "header": "", "role": "other", "unit_hint": None} for i in range(len(grid[0]))]

    ref = item.get("self_ref")
    rows = []
    for r in range(n_header, len(grid)):
        cells = [normalize_text(c) for c in grid[r]]
        rows.append({"row_id": None, "cells": cells, "kind": "data", "section": None,
                     "origin_cols": [meta[r][c]["origin"][1] for c in range(len(cells))],
                     "source_ref": ref, "source_row": r, "filled": [],
                     "row_section_flag": any(m["row_section"] for m in meta[r])})
    table = {
        "id": table_id,
        "source_refs": [ref],
        "provenance": doc.provenance(item),
        "caption": normalize_text(doc.caption_text(item)),
        "section_path": [],
        "category": None,
        "header_rows": n_header,
        "header_texts": [normalize_text(h) for h in headers],
        "columns": columns,
        "rows": rows,
        "footnotes": {},
        "footnote_texts": [normalize_text(t) for t in doc.footnote_texts(item)],
        "flags": [],
        "merge_log": [],
    }
    if n_header == 0:
        table["flags"].append("no_header_detected")
    return table


def _value_col_idx(table: dict) -> list[int]:
    return [c["index"] for c in table["columns"]
            if c["role"].split("_")[0] in ("min", "typ", "max", "value")]


def classify_rows(table: dict, cfg: dict) -> None:
    """標記 section / repeated_header / empty，並做 fill-down。"""
    tcfg = cfg["tables"]
    value_cols = _value_col_idx(table)
    header_norm = [h.lower() for h in table["header_texts"]]
    header_last = [h.split(" / ")[-1].lower() for h in table["header_texts"]]
    current_section = None
    last_data: dict | None = None
    role_idx = {c["role"]: c["index"] for c in table["columns"]}

    for row in table["rows"]:
        cells = row["cells"]
        non_empty = [c for c in cells if c]
        if not non_empty:
            row["kind"] = "empty"
            continue
        low = [c.lower() for c in cells]
        if tcfg.get("drop_repeated_headers") and header_norm and (
                low == header_norm or low == header_last or
                sum(1 for a, b in zip(low, header_last) if a and a == b) >= max(2, int(0.6 * len(non_empty)))):
            row["kind"] = "repeated_header"
            continue
        has_value = any(cells[i] for i in value_cols if i < len(cells))
        distinct = set(non_empty)
        if row["row_section_flag"] or (len(distinct) == 1 and not has_value and len(cells) > 2
                                       and not NUM_TOKEN_RE.fullmatch(non_empty[0])):
            row["kind"] = "section"
            current_section = non_empty[0]
            row["section"] = current_section
            continue
        row["section"] = current_section
        if has_value and last_data is not None:
            # 只有「參數名稱格是空的」才視為上一列合併儲存格的延續；
            # 有自己名稱的列不繼承上一列的 conditions（避免把別的參數條件套進來）
            p_idx = role_idx.get("parameter")
            continuation = p_idx is None or not cells[p_idx]
            if continuation:
                for role in tcfg.get("fill_down_roles", []):
                    i = role_idx.get(role)
                    if i is not None and not cells[i] and last_data["cells"][i]:
                        cells[i] = last_data["cells"][i]
                        row["filled"].append(i)
        if has_value:
            last_data = row


def assign_row_ids(table: dict) -> None:
    for i, row in enumerate(table["rows"]):
        row["row_id"] = f"{table['id']}.R{i}"


# ---------------------------------------------------- continuation merge
def _is_continuation_caption(caption: str, patterns: list[str]) -> bool:
    low = caption.lower()
    return any(p.lower() in low for p in patterns)


def _table_no(caption: str) -> str | None:
    m = _TABLE_NO_RE.search(caption or "")
    return m.group(1) if m else None


def _should_merge(prev: dict, nxt: dict, between_texts: int, cfg: dict,
                  cont_text: bool = False) -> tuple[bool, str]:
    pats = cfg["tables"]["continuation_patterns"]
    prev_last_page = max(p["page"] for p in prev["provenance"]) if prev["provenance"] else None
    nxt_first_page = min(p["page"] for p in nxt["provenance"]) if nxt["provenance"] else None
    if prev_last_page is None or nxt_first_page is None:
        return False, "no_provenance"
    page_gap = nxt_first_page - prev_last_page
    cont_caption = _is_continuation_caption(nxt["caption"], pats)
    same_no = _table_no(prev["caption"]) is not None and _table_no(prev["caption"]) == _table_no(nxt["caption"])
    same_cols = len(prev["columns"]) == len(nxt["columns"])
    header_ok = (nxt["header_rows"] == 0 or
                 [h.lower() for h in nxt["header_texts"]] == [h.lower() for h in prev["header_texts"]])
    if page_gap not in (0, 1):
        return False, "page_gap"
    if not same_cols:
        return False, "column_count_differs" if (cont_caption or same_no) else "different_table"
    if cont_caption or same_no:
        return True, "caption_continuation" if cont_caption else "same_table_number"
    if cont_text and header_ok and page_gap == 1:
        return True, "continued_text_between"      # 例：表格下方 "Continued – next page"
    if not nxt["caption"] and between_texts == 0 and header_ok:
        return True, "adjacent_no_caption_same_columns"
    return False, "different_table"


def _merge_into(prev: dict, nxt: dict, reason: str) -> None:
    if nxt["header_rows"] == 0 and prev["header_rows"] > 0:
        # 被切斷的後半段沒有表頭 → 第一列其實是 data，沿用前表欄位定義
        pass
    prev["source_refs"].extend(nxt["source_refs"])
    prev["provenance"].extend(nxt["provenance"])
    prev["rows"].extend(nxt["rows"])
    prev["footnote_texts"].extend(nxt["footnote_texts"])
    prev["merge_log"].append({"merged": nxt["source_refs"], "reason": reason,
                              "caption": nxt["caption"], "pages": [p["page"] for p in nxt["provenance"]]})
    if nxt["columns"] and any(c["role"] != "other" for c in nxt["columns"]) and \
            all(c["role"] == "other" for c in prev["columns"]):
        prev["columns"] = nxt["columns"]


# ------------------------------------------------------------- notes
def parse_note_block(text: str) -> dict[str, str]:
    """'Notes: 1. xxx 2. yyy' → {'1': 'xxx', '2': 'yyy'}"""
    text = re.sub(r"^\s*notes?\s*[:.]?\s*", "", normalize_text(text), flags=re.I)
    matches = list(_NOTE_ITEM_RE.finditer(" " + text))
    if not matches:
        return {"*": text} if text else {}
    out = {}
    padded = " " + text
    for i, m in enumerate(matches):
        nid = m.group(1) or m.group(2)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(padded)
        out[nid] = padded[m.end():end].strip()
    return out


# ------------------------------------------------------------- driver
def extract_tables(doc: DoclingDoc, cfg: dict) -> tuple[list[dict], dict]:
    """Return (normalized_tables, log)."""
    tables: list[dict] = []
    log: dict[str, Any] = {"merges": [], "not_merged_continuations": [], "raw_table_count": 0}
    heading_stack: list[tuple[int, str]] = []
    between_texts = 0
    cont_text = False
    last_table: dict | None = None
    collecting_notes_for: dict | None = None
    idx = 0

    for item in doc.iter_body():
        ref = item.get("self_ref", "")
        label = item.get("label", "")
        if ref.startswith("#/texts"):
            text = normalize_text(item.get("text", ""))
            if label in ("section_header", "title"):
                level = int(item.get("level", 1) or 1)
                heading_stack = [h for h in heading_stack if h[0] < level] + [(level, text)]
                collecting_notes_for = None
                cont_text = False
                between_texts += 1
            elif label == "caption":
                continue                                # captions 已透過 table.captions 讀取
            elif label in ("page_header", "page_footer"):
                continue
            else:
                if collecting_notes_for is not None and (label == "footnote" or _NOTE_START_RE.match(text)):
                    collecting_notes_for["footnote_texts"].append(text)
                    continue
                collecting_notes_for = None
                between_texts += 1
                if _is_continuation_caption(text, cfg["tables"]["continuation_patterns"]):
                    cont_text = True
            continue
        if not ref.startswith("#/tables"):
            between_texts += 1 if ref.startswith("#/pictures") else 0
            collecting_notes_for = None
            continue

        log["raw_table_count"] += 1
        t = normalize_table(doc, item, f"T{idx}", cfg)
        t["section_path"] = [h[1] for h in heading_stack]
        merged = False
        if last_table is not None and cfg["tables"].get("merge_continuations", True):
            ok, reason = _should_merge(last_table, t, between_texts, cfg, cont_text)
            if ok:
                _merge_into(last_table, t, reason)
                log["merges"].append({"into": last_table["id"], "from": t["source_refs"], "reason": reason})
                merged = True
            elif reason == "column_count_differs":
                t["flags"].append("continuation_not_merged:column_count_differs")
                log["not_merged_continuations"].append({"table": t["source_refs"], "prev": last_table["id"]})
        if not merged:
            tables.append(t)
            last_table = t
            idx += 1
        collecting_notes_for = last_table
        between_texts = 0
        cont_text = False

    for t in tables:
        for row in t["rows"]:
            row.setdefault("row_section_flag", False)
        classify_rows(t, cfg)
        assign_row_ids(t)
        notes: dict[str, str] = {}
        for txt in t["footnote_texts"]:
            notes.update(parse_note_block(txt))
        t["footnotes"] = notes
        t["pages"] = sorted({p["page"] for p in t["provenance"]})
    return tables, log


def table_to_markdown(table: dict, with_row_ids: bool = True) -> str:
    """給 LLM / review 用。每列帶 row_id，讓 LLM 輸出可追溯。"""
    headers = [c["header"] or f"col{c['index']}" for c in table["columns"]]
    if with_row_ids:
        headers = ["row_id"] + headers
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for row in table["rows"]:
        if row["kind"] == "empty":
            continue
        cells = [c.replace("|", "\\|") for c in row["cells"]]
        if with_row_ids:
            cells = [row["row_id"]] + cells
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)
