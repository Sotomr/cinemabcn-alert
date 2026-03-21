import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from utils import film_title_dedupe_key, normalize_title


def test_normalize_strips_vose():
    assert "your name" in normalize_title("Your Name (VOSE)")


def test_normalize_removes_accents_for_compare():
    a = normalize_title("Águilas de El Cairo")
    b = normalize_title("aguilas de el cairo")
    assert a == b


def test_film_title_dedupe_key_merges_vose_variants():
    a = film_title_dedupe_key("Your Name (VOSE)")
    b = film_title_dedupe_key("Your name VOSE")
    assert a == b


def test_film_title_dedupe_key_merges_doblada():
    a = film_title_dedupe_key("Little Amélie Doblada ESP")
    b = film_title_dedupe_key("Little Amélie")
    assert a == b
