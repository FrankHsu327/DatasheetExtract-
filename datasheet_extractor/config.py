"""Config loading: config/default.yaml deep-merged with config/components/<component>.yaml."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_config(component: str | None = None, extra: str | Path | None = None) -> dict[str, Any]:
    cfg = yaml.safe_load((CONFIG_DIR / "default.yaml").read_text(encoding="utf-8"))
    if component:
        comp_path = CONFIG_DIR / "components" / f"{component}.yaml"
        if not comp_path.exists():
            raise FileNotFoundError(f"Unknown component config: {comp_path}")
        cfg = _deep_merge(cfg, yaml.safe_load(comp_path.read_text(encoding="utf-8")))
    if extra:
        cfg = _deep_merge(cfg, yaml.safe_load(Path(extra).read_text(encoding="utf-8")))
    cfg.setdefault("component", {})["name"] = component or cfg.get("component", {}).get("name", "generic")
    return cfg
