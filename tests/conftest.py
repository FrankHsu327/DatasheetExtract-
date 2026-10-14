import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def sample_paths():
    pdf = ROOT / "samples" / "DS325Q32.pdf"
    dj = ROOT / "samples" / "DS325Q32.docling.json"
    gold = ROOT / "golden" / "DS325Q32.golden.json"
    if not (pdf.exists() and dj.exists() and gold.exists()):
        subprocess.check_call([sys.executable, str(ROOT / "scripts" / "make_sample.py")])
    return pdf, dj, gold


@pytest.fixture()
def cfg():
    from datasheet_extractor.config import load_config
    return load_config("spi_rom")
