import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from diff_engine import compute_new_entries
from models import Film


def test_new_entries():
    prev = [
        Film("Verdi", "Film A", "http://a", "c"),
        Film("Verdi", "Film B", "http://b", "c"),
    ]
    cur = prev + [Film("Verdi", "Film C", "http://c", "c")]
    new = compute_new_entries(prev, cur)
    assert len(new) == 1
    assert new[0].title == "Film C"


def test_duplicate_titles_same_cinema_deduped_in_diff():
    cur = [
        Film("Verdi", "Same", "http://1", "c"),
        Film("Verdi", "Same", "http://2", "c"),
    ]
    new = compute_new_entries([], cur)
    assert len(new) == 1
