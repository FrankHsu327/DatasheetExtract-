"""Figures — 收集圖片、判斷圖類型、連結相關參數。

圖片描述與分類來自 Stage 1 後端的內建功能（見 docs/METHOD_COMPARISON.md）：
- docling：Docling picture classifier + picture description（Granite Vision 3.3 2B，Docling 預設 prompt）
- hybrid：Docling picture classifier + Granite Vision（datasheet prompt，帶入 caption 與圖內 PDF 文字）
- pdfplumber：沒有（只依 caption 推估圖範圍）
describe_figures() 是另外串公司視覺 LLM 的選項，預設關閉。

設計決策（盲點對策）：
- 圖不是 spec 數值的主要來源。Timing diagram 上的參數符號（tCLQV…）幾乎都會出現在 AC 表，
  所以數值以表格為準，圖只負責「連結」與「描述」。
- Typical characteristics 曲線不做數位化（typical 值不能當 EA pass/fail 依據）。
- 若視覺模型描述中出現數值，一律 needs_review=True。
- Docling 可能把「畫成圖的表格」判成 picture：caption 以 Table 開頭的 picture 會被標記
  suspected_table_as_picture，交給 review / 視覺 LLM 轉錄。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .docling_reader import DoclingDoc
from .text_normalize import normalize_text

_SYMBOL_RE = re.compile(r"\bt[A-Z][A-Z0-9]{1,6}\b")


def _classification(item: dict) -> str | None:
    # 舊格式：annotations[kind=classification]；新格式：meta.classification
    for ann in item.get("annotations", []) or []:
        if ann.get("kind") == "classification":
            classes = ann.get("predicted_classes") or []
            if classes:
                return max(classes, key=lambda c: c.get("confidence", 0)).get("class_name")
    meta = item.get("meta") or {}
    cls = meta.get("classification") or {}
    preds = cls.get("predictions") or []
    if preds:
        return max(preds, key=lambda c: c.get("confidence", 0)).get("class_name")
    return None


def picture_description(item: dict) -> str | None:
    """Stage 1 後端產生的圖片描述（meta.description；舊格式 annotations kind=description）。"""
    meta = item.get("meta") or {}
    desc = meta.get("description") or {}
    if isinstance(desc, dict) and desc.get("text"):
        return desc["text"].strip()
    for ann in item.get("annotations", []) or []:
        if ann.get("kind") == "description" and ann.get("text"):
            return ann["text"].strip()
    return None


def picture_class(item: dict) -> str | None:
    return _classification(item)


def _kind_from_caption(caption: str, kinds: dict[str, list[str]]) -> str | None:
    low = caption.lower()
    if "power" in low and any(k in low for k in ("up", "on", "down", "sequence")):
        return "power_sequence"
    for kind, kws in kinds.items():
        if any(k in low for k in kws):
            return kind
    return None


def collect_figures(doc: DoclingDoc, cfg: dict, figures_dir: Path | None = None) -> list[dict[str, Any]]:
    fcfg = cfg["figures"]
    figures = []
    heading = None
    for item in doc.iter_body():
        ref = item.get("self_ref", "")
        if ref.startswith("#/texts") and item.get("label") == "section_header":
            heading = normalize_text(item.get("text"))
            continue
        if not ref.startswith("#/pictures"):
            continue
        idx = int(ref.split("/")[-1])
        caption = normalize_text(doc.caption_text(item))
        inner = [normalize_text(t) for t in doc.child_texts(item)]
        symbols = sorted(set(_SYMBOL_RE.findall(caption + " " + " ".join(inner))))
        kind = _kind_from_caption(caption + " " + (heading or ""), fcfg["kinds"])
        image_path = None
        if figures_dir is not None:
            p = figures_dir / f"figure_{idx}.png"
            image_path = str(p) if p.exists() else None
        fig = {
            "id": f"F{idx}",
            "source_ref": ref,
            "provenance": doc.provenance(item),
            "caption": caption or None,
            "section": heading,
            "kind": kind,
            "docling_class": _classification(item),
            "inner_text": inner[:200],
            "linked_symbols": symbols,
            "image_path": image_path,
            "description": picture_description(item),
            "needs_review": kind in set(fcfg.get("needs_review_kinds", [])),
            "flags": [],
        }
        if re.match(r"^\s*table\b", caption, re.I):
            fig["flags"].append("suspected_table_as_picture")
            fig["needs_review"] = True
        # VLM 描述裡的數字可能是從曲線「讀」出來的估計值：
        # 圖不是 spec 數值來源，一律人工確認
        if fig["description"] and re.search(r"\d+(\.\d+)?\s*(m|µ|u|n|p|k|M)?(V|A|Hz|s|W|Ω|°C|%)\b", fig["description"]):
            fig["flags"].append("numbers_in_description")
            fig["needs_review"] = True
        figures.append(fig)
    return figures


def link_figures_to_parameters(figures: list[dict], parameters: list[dict]) -> None:
    by_symbol: dict[str, list[str]] = {}
    for p in parameters:
        if p.get("symbol"):
            by_symbol.setdefault(p["symbol"].lower(), []).append(p["id"])
    for f in figures:
        f["linked_parameters"] = sorted({pid for s in f["linked_symbols"] for pid in by_symbol.get(s.lower(), [])})
        missing = [s for s in f["linked_symbols"] if s.lower() not in by_symbol]
        if missing:
            f["flags"].append("symbols_in_figure_not_in_tables:" + ",".join(missing))


def describe_figures(figures: list[dict], cfg: dict) -> None:
    """圖片描述。預設關閉（figures.describe_enabled=false）。

    TODO(Devin): 二選一串接，完成後把 config figures.describe_enabled 改 true。

    ── 方案 A：moondream（本機）────────────────────────────────────────────
    Devin 環境連不到 HuggingFace → 先在可上網的機器下載權重，放到內網路徑再 from_pretrained(local_path)

    # from PIL import Image
    # from transformers import AutoModelForCausalLM
    # model = AutoModelForCausalLM.from_pretrained(
    #     "/models/moondream2",            # 預先下載的本地路徑（原 repo: vikhyatk/moondream2）
    #     trust_remote_code=True,
    #     # revision="<pin 一個版本>",       # 務必 pin revision，remote code 會變
    # )
    # for f in figures:
    #     if not f["image_path"] or f["kind"] in ("package",):
    #         continue
    #     img = Image.open(f["image_path"])
    #     prompt = _figure_prompt(f, cfg)
    #     answer = model.query(img, prompt)["answer"]
    #     f["description"] = _parse_figure_answer(answer)
    #     if f["description"] and f["description"].get("numeric_values_visible"):
    #         f["needs_review"] = True
    #
    # 注意：moondream 這類小模型可描述圖，但讀不準 timing diagram 上的小字/數值。
    #       timing 數值請以 AC 表為準，這裡只用來補 signals / timing_symbols / summary。

    ── 方案 B：公司視覺 LLM（OpenAI-compatible，若支援 image input）──────
    # import base64, requests, os
    # b64 = base64.b64encode(open(f["image_path"], "rb").read()).decode()
    # payload = {"model": os.environ["COMPANY_VLM_MODEL"], "temperature": 0, "messages": [
    #     {"role": "user", "content": [
    #         {"type": "text", "text": _figure_prompt(f, cfg)},
    #         {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]}
    # r = requests.post(os.environ["COMPANY_VLM_URL"], json=payload,
    #                   headers={"Authorization": f"Bearer {os.environ['COMPANY_VLM_TOKEN']}"}, timeout=120)
    # f["description"] = _parse_figure_answer(r.json()["choices"][0]["message"]["content"])

    ── 方案 C：在 hybrid Stage 1 改用公司視覺 LLM ──
    vision_describe.GraniteVision 換成呼叫公司端點的類別（同樣的 describe(image, prompt) 介面）。

    ── 額外：suspected_table_as_picture 的轉錄 ───────────────────────────────
    # 對 flags 含 suspected_table_as_picture 的圖，用視覺 LLM 要求輸出 markdown table，
    # 再丟回 stage2 的 normalize 流程（建議另存 tables_from_images.json，並強制人工 review）。
    """
    if not cfg["figures"].get("describe_enabled"):
        return
    raise NotImplementedError("Figure description not wired yet — see TODO(Devin) in figures.describe_figures")


def _figure_prompt(fig: dict, cfg: dict) -> str:
    tpl_path = Path(__file__).resolve().parent.parent / cfg["figures"]["prompt_file"]
    tpl = tpl_path.read_text(encoding="utf-8") if tpl_path.exists() else "Describe this datasheet figure."
    return tpl.replace("{{CAPTION}}", fig.get("caption") or "(none)").replace("{{KIND}}", str(fig.get("kind")))


def _parse_figure_answer(text: str) -> dict | None:
    try:
        text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
        return json.loads(text)
    except Exception:  # noqa: BLE001
        return {"summary": text}
