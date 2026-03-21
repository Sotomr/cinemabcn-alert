import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from utils import normalize_title


def test_normalize_strips_vose():
    assert "your name" in normalize_title("Your Name (VOSE)")


def test_normalize_removes_accents_for_compare():
    a = normalize_title("Águilas de El Cairo")
    b = normalize_title("aguilas de el cairo")
    assert a == b
