"""Summarize the shape of a JSON file (keys, types, sample values) — for reverse-engineering tool outputs."""
import json
import sys


def shape(x, depth=0, max_depth=6, key=""):
    pad = "  " * depth
    if depth > max_depth:
        return
    if isinstance(x, dict):
        print(f"{pad}{key}{{}} keys={list(x)[:25]}")
        for k, v in list(x.items())[:25]:
            if isinstance(v, (dict, list)):
                shape(v, depth + 1, max_depth, f"{k}: ")
            else:
                print(f"{pad}  {k}: {type(v).__name__} = {str(v)[:120]!r}")
    elif isinstance(x, list):
        print(f"{pad}{key}[] len={len(x)}")
        if x:
            shape(x[0], depth + 1, max_depth, "[0]: ")
            if len(x) > 1 and isinstance(x[0], dict) and isinstance(x[1], dict) and set(x[1]) != set(x[0]):
                shape(x[1], depth + 1, max_depth, "[1]: ")


data = json.load(open(sys.argv[1], encoding="utf-8"))
shape(data, max_depth=int(sys.argv[2]) if len(sys.argv) > 2 else 6)
