"""Stage 3a — 定位：依 caption、章節路徑、表頭把每張表分類。

分類失敗不會丟掉表格：category=None 的表格仍保留在 component.json 的 tables 裡給 chatbot 用，
若具有 min/typ/max 欄位（spec-like）也會進入抽取。
"""
from __future__ import annotations


def _score(text: str, keywords: list[str]) -> int:
    low = text.lower()
    return sum(1 for k in keywords if k in low)


def categorize_table(table: dict, cfg: dict) -> tuple[str | None, dict]:
    cats = cfg["locate"]["categories"]
    sources = {
        "caption": (table.get("caption") or "", 3),
        "section": (" > ".join(table.get("section_path", [])[-2:]), 2),
        "header": (" ".join(table.get("header_texts", [])), 1),
    }
    scores: dict[str, int] = {}
    for cat, kws in cats.items():
        s = sum(_score(text, kws) * w for text, w in sources.values())
        if s:
            scores[cat] = s
    if not scores:
        return None, {}
    best = max(scores.items(), key=lambda kv: kv[1])
    return best[0], scores


def is_spec_like(table: dict) -> bool:
    roles = {c["role"].split("_")[0] for c in table["columns"]}
    return bool(roles & {"min", "typ", "max", "value"}) and bool(roles & {"parameter", "symbol"})


def locate(tables: list[dict], cfg: dict) -> None:
    spec_cats = set(cfg["locate"]["spec_categories"])
    for t in tables:
        cat, scores = categorize_table(t, cfg)
        t["category"] = cat
        t["category_scores"] = scores
        t["spec_like"] = is_spec_like(t)
        t["extract"] = (cat in spec_cats) or (cat is None and cfg["extract"].get("extract_all_spec_like")
                                              and t["spec_like"])
        if cat is None and t["spec_like"]:
            t["flags"].append("spec_like_but_uncategorized")
        if cat in spec_cats and not t["spec_like"]:
            t["flags"].append("spec_category_but_columns_unrecognized")
