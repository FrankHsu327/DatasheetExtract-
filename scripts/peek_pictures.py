"""List pictures in a document.json with page, class, caption and description (first chars)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datasheet_extractor.docling_reader import DoclingDoc  # noqa: E402
from datasheet_extractor.figures import picture_class, picture_description  # noqa: E402

doc = DoclingDoc.load(sys.argv[1])
pics = doc.data.get("pictures", [])
n_desc = 0
for i, p in enumerate(pics):
    prov = doc.provenance(p)
    d = picture_description(p)
    n_desc += bool(d)
    print(f"#{i} p{prov[0]['page'] if prov else '?'} class={picture_class(p)} cap={doc.caption_text(p)[:60]!r}")
    print("     desc:", (d or "-")[:300].replace("\n", " "))
print(f"{len(pics)} pictures, {n_desc} described")
