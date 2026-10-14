"""Normalization of datasheet cell text: symbols, footnote markers, units, numeric values.

盲點對策：
- µ (U+00B5) / μ (U+03BC) / 'u' 混用 → 統一
- Ω (U+2126) / Ω (U+03A9) / 'ohm' → 統一
- −, –, — 等負號/破折號 → '-'
- 註腳上標黏在數值上（2.0(1)、2.0¹、2.0 Note 1）→ 拆出 notes，避免 2.0 被讀成 2.01
- 原始字串一律保留在 raw，正規化失敗也不丟資料
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

_DASHES = dict.fromkeys(map(ord, "\u2212\u2013\u2014\u2012\u2010\u2011\uFE63\uFF0D"), "-")
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff\u00ad"), None)
_SUPERSCRIPT_DIGITS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
_SUP_MAP = {c: str(i) for i, c in enumerate(_SUPERSCRIPT_DIGITS)}
EMPTY_TOKENS = {"", "-", "—", "–", "n/a", "na", "/", "--", "---", "—-"}


_LATEX_CMDS = {r"\circ": "°", r"\mu": "µ", r"\pm": "±", r"\Omega": "Ω", r"\leq": "≤", r"\le": "≤",
               r"\geq": "≥", r"\ge": "≥", r"\times": "×", r"\sim": "~", r"\%": "%", r"\ ": " ", r"\,": " "}
_LATEX_WRAP_RE = re.compile(r"\\(?:mathrm|mathsf|mathbf|mathit|text|textrm|operatorname)\s*\{([^{}]*)\}")
_LATEX_FOOTNOTE_RE = re.compile(r"\^\{\s*\(?\s*(\d+)\s*\)?\s*\}")
_LATEX_SUPSUB_RE = re.compile(r"[_^]\{([^{}]*)\}")
_LATEX_SUPSUB1_RE = re.compile(r"[_^](\w)")


_MATH_RE = re.compile(r"\$([^$]*)\$")


def _delatex_math(m: str) -> str:
    for k, v in _LATEX_CMDS.items():
        m = m.replace(k, v)
    for _ in range(6):   # 由內而外：\mathsf{V_{DD}} 需要多輪
        prev = m
        m = _LATEX_WRAP_RE.sub(r"\1", m)
        m = _LATEX_FOOTNOTE_RE.sub(lambda x: "".join(_SUPERSCRIPT_DIGITS[int(d)] for d in x.group(1)), m)
        m = _LATEX_SUPSUB_RE.sub(r"\1", m)
        m = _LATEX_SUPSUB1_RE.sub(r"\1", m)
        if m == prev:
            break
    return m.replace("{", "").replace("}", "")


def delatex(s: str) -> str:
    """VLM（或 VLM 產生的文件）常把 symbol 寫成 LaTeX：$t_{VSL}^{(1)}$ → tVSL⁽1⁾、F$_{R}$ → FR、
    $\\mathsf { V _ { D D } } = 5 \\mathsf { V }$ → VDD = 5V（數學模式內的空白不算數）。"""
    if "$" not in s and "\\" not in s:
        return s
    if "$" not in s:   # 沒有數學模式：只換指令（\mu、\Omega…），不動底線（VCC_PS4）
        for k, v in _LATEX_CMDS.items():
            s = s.replace(k, v)
        return _LATEX_WRAP_RE.sub(r"\1", s)

    def math(m: re.Match) -> str:
        body = re.sub(r"\s+", "", m.group(1).replace("\\ ", "\u0002"))
        body = _delatex_math(body).replace("\u0002", " ")
        return re.sub(r"([=<>≤≥])", r" \1 ", body)
    s = _MATH_RE.sub(math, s)
    return re.sub(r" {2,}", " ", s.replace("$", ""))


def normalize_text(s: str | None) -> str:
    if not s:
        return ""
    s = delatex(s.translate(_ZERO_WIDTH).translate(_DASHES))
    # 先保護上標數字（NFKC 會把 ¹ 變成 1，導致註腳黏到數值）
    s = "".join(f"\u0000{_SUP_MAP[c]}\u0001" if c in _SUP_MAP else c for c in s)
    s = unicodedata.normalize("NFKC", s)          # µ→μ, Ω→Ω, full-width → ASCII
    s = s.replace("\u0000", "⁽").replace("\u0001", "⁾")  # 上標改成可辨識的 ⁽n⁾ 標記
    s = s.replace("μ", "µ")                        # 統一用 micro sign
    s = s.replace("∆", "Δ")                   # ∆ (INCREMENT) → Δ（ΔVUVLO 等 symbol）
    s = re.sub(r"\s+", " ", s).strip()
    return s


_FOOTNOTE_PATTERNS = [
    re.compile(r"\s*⁽(\d+)⁾$"),                    # protected superscript
    re.compile(r"\s*\((\d{1,2})\)$"),              # 2.0(1)
    re.compile(r"\s*\[(\d{1,2})\]$"),              # 2.0[1]
    re.compile(r"\s+note\s*(\d{1,2})$", re.I),     # 2.0 Note 1
]


def split_footnotes(s: str) -> tuple[str, list[str]]:
    """Strip trailing footnote markers. Returns (clean_text, [note ids])."""
    notes: list[str] = []
    changed = True
    while changed and s:
        changed = False
        for pat in _FOOTNOTE_PATTERNS:
            m = pat.search(s)
            if m and m.start() > 0:       # 不處理整格只有 "(1)" 的情況
                notes.insert(0, m.group(1))
                s = s[: m.start()].rstrip()
                changed = True
    s = s.replace("⁽", "").replace("⁾", "")       # 中間殘留的上標標記
    return s, notes


# ---------------------------------------------------------------- units
_PREFIX = {"p": 1e-12, "n": 1e-9, "µ": 1e-6, "u": 1e-6, "m": 1e-3, "": 1.0, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9}
_BASE = {"V": "V", "A": "A", "W": "W", "s": "s", "Hz": "Hz", "F": "F", "Ω": "Ω", "ohm": "Ω", "Ohm": "Ω",
         "B": "B", "bit": "bit", "b": "bit"}
_SPECIAL_CS = {  # case-sensitive
    "C": ("°C", 1.0), "Kb": ("bit", 1e3), "Mb": ("bit", 1e6), "Gb": ("bit", 1e9),
    "KB": ("B", 1e3), "MB": ("B", 1e6),
}
_SPECIAL_CI = {  # case-insensitive (keys lowercase)
    "°c": ("°C", 1.0), "℃": ("°C", 1.0), "degc": ("°C", 1.0), "deg c": ("°C", 1.0),
    "%": ("%", 1.0), "cycles": ("cycles", 1.0), "cycle": ("cycles", 1.0), "years": ("years", 1.0),
    "v/ns": ("V/s", 1e9), "v/ms": ("V/s", 1e3), "v/µs": ("V/s", 1e6), "v/us": ("V/s", 1e6), "mv/µs": ("V/s", 1e3),
    "kbit": ("bit", 1e3), "mbit": ("bit", 1e6), "mbits": ("bit", 1e6), "gbit": ("bit", 1e9),
    "sec": ("s", 1.0), "clk": ("cycles", 1.0), "clocks": ("cycles", 1.0),
}
_UNIT_RE = re.compile(r"^(p|n|µ|u|m|k|K|M|G)?(V|A|W|s|Hz|F|Ω|ohm|Ohm|B|bit)$")


def parse_unit(u: str | None) -> dict[str, Any] | None:
    """'µA' → {'unit': 'µA', 'si_unit': 'A', 'factor': 1e-6}. None if unknown/empty."""
    if not u:
        return None
    u = normalize_text(u).strip().strip("()[]").strip()
    if not u:
        return None
    if u in _SPECIAL_CS:
        si, f = _SPECIAL_CS[u]
        return {"unit": u if u != "C" else "°C", "si_unit": si, "factor": f}
    if u.lower() in _SPECIAL_CI:
        si, f = _SPECIAL_CI[u.lower()]
        return {"unit": u, "si_unit": si, "factor": f}
    m = _UNIT_RE.match(u.replace(" ", ""))
    if m:
        prefix, base = m.group(1) or "", m.group(2)
        display = (prefix.replace("u", "µ") + _BASE[base]) if base not in ("ohm", "Ohm") else prefix + "Ω"
        return {"unit": display, "si_unit": _BASE[base], "factor": _PREFIX[prefix]}
    return None


# -------------------------------------------------------------- values
_NUM = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_VALUE_RE = re.compile(rf"^(?P<pm>±)?\s*(?P<num>{_NUM})\s*(?P<unit>[A-Za-zµΩ°℃%/]+(?:\s?[A-Za-z]+)?)?$")
NUM_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9.])[+-]?\d+(?:\.\d+)?")


def parse_value(raw: str | None, default_unit: str | None = None) -> dict[str, Any] | None:
    """Parse one spec cell. Always keeps raw. Returns None for empty/dash cells.

    Output: {raw, value, unit, value_si, si_unit, expr, notes, plus_minus}
      - value=None + expr=str 代表是表達式（例如 0.7×VCC、VCC+0.4），保留給人或 LLM 判讀
    """
    text = normalize_text(raw)
    if text.lower() in EMPTY_TOKENS:
        return None
    clean, notes = split_footnotes(text)
    if clean.lower() in EMPTY_TOKENS:
        return {"raw": raw, "value": None, "unit": None, "value_si": None, "si_unit": None,
                "expr": None, "notes": notes, "plus_minus": False}
    out: dict[str, Any] = {"raw": raw, "value": None, "unit": None, "value_si": None, "si_unit": None,
                           "expr": None, "notes": notes, "plus_minus": False}
    clean = re.sub(r"(?<=\d),(?=\d{3}\b)", "", clean)   # 1,000 → 1000
    if clean.upper().replace(" ", "") in ("D.C.", "DC"):   # 時脈下限 D.C. = 0 Hz
        clean = "0"
    m = _VALUE_RE.match(clean)
    unit_info = None
    if m:
        out["value"] = float(m.group("num"))
        out["plus_minus"] = bool(m.group("pm"))
        unit_info = parse_unit(m.group("unit")) if m.group("unit") else parse_unit(default_unit)
        if m.group("unit") and unit_info is None:
            # 數字後面接了無法辨識的字 → 當表達式保留
            out["value"], out["expr"] = None, clean
            unit_info = parse_unit(default_unit)
    else:
        out["expr"] = clean
        unit_info = parse_unit(default_unit)
    if unit_info:
        out["unit"], out["si_unit"] = unit_info["unit"], unit_info["si_unit"]
        if out["value"] is not None:
            out["value_si"] = float(f"{out['value'] * unit_info['factor']:.12g}")
    elif default_unit:
        out["unit"] = normalize_text(default_unit)
    return out


def unit_from_header(header: str) -> str | None:
    """'Max (ns)' / 'Limit [µA]' → 'ns' / 'µA'."""
    m = re.search(r"[\(\[]\s*([^\)\]]+?)\s*[\)\]]\s*$", normalize_text(header))
    if m and parse_unit(m.group(1)):
        return m.group(1)
    return None


def normalize_symbol(s: str) -> str:
    s = normalize_text(s)
    s, _ = split_footnotes(s)
    return s.replace(" ", "")


def numeric_tokens(s: str) -> list[str]:
    """Number tokens used for cross-check (normalized: strip trailing zeros)."""
    toks = []
    for t in NUM_TOKEN_RE.findall(normalize_text(s)):
        t = t.lstrip("+")
        if "." in t:
            t = t.rstrip("0").rstrip(".")
        toks.append(t or "0")
    return toks


_RANGE_RE = re.compile(rf"^\s*({_NUM})\s*(?:to|~|\.\.|…)\s*({_NUM})\s*([A-Za-zµΩ°℃%/]*)\s*$", re.I)


def parse_range(raw: str | None) -> tuple[str, str, str | None] | None:
    """'-0.5 to 4.0' / '-65 ~ 150 °C' → ('-0.5', '4.0', unit|None)."""
    if not raw:
        return None
    clean, _ = split_footnotes(normalize_text(raw))
    m = _RANGE_RE.match(clean)
    if not m:
        return None
    return m.group(1), m.group(2), (m.group(3) or None)


_UNIT_WORDS = r"(?:V|mV|µV|A|mA|µA|uA|nA|W|mW|s|ms|µs|us|ns|ps|Hz|kHz|MHz|GHz|pF|nF|µF|°C|%|Ω|kΩ)"
_SPEC_TOKEN_RE = re.compile(rf"(?<![A-Za-z0-9.])(?:[+-]?\d+\.\d+(?:\s?{_UNIT_WORDS})?|[+-]?\d+\s?{_UNIT_WORDS})(?![A-Za-z0-9])")
_DOT_LEADER_RE = re.compile(r"\.{4,}")


def spec_value_tokens(s: str) -> list[str]:
    """像規格值的 token：帶小數點（2.7）或帶單位（50 MHz、10µA）。
    單純整數（時序圖 bit 編號、頁碼、位址）不算，用於 diagnose 降低誤報。"""
    s = normalize_text(s)
    if _DOT_LEADER_RE.search(s):            # 目錄行
        return []
    return _SPEC_TOKEN_RE.findall(s)
