import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from classifiers import PRIMARY_SPECIAL_EVENT, classify_film
from datetime import date
from models import Film


def test_special_keyword():
    f = Film(
        cinema="Verdi",
        title="Clásico: Casablanca",
        url="http://x",
        source_section="cartelera",
    )
    c = classify_film(
        f,
        previous_titles_norm=frozenset(),
        week_start=date(2026, 1, 1),
        week_end=date(2026, 1, 7),
    )
    assert c.primary == PRIMARY_SPECIAL_EVENT
