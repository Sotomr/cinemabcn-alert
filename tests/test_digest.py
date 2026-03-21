import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from digest import _global_top_lines, parse_show_date, parse_show_time, score_from_rating_html
from models import Show


def test_parse_verdi_show():
    s = Show(datetime="20260321 20:30")
    assert parse_show_date(s) == date(2026, 3, 21)
    assert parse_show_time(s) == "20:30"


def test_score_from_rating_html():
    assert score_from_rating_html("★ 7.5 TMDb (10 votos) IMDb") == 7.5
    assert score_from_rating_html(None) == -1.0
    assert score_from_rating_html("") == -1.0


def test_global_top_merges_same_film_across_cinemas():
    rating = "★ 8.5 TMDb (10 votos) IMDb"
    block = {
        "Verdi": [("Your name VOSE", ["20:30"], rating)],
        "Maldà": [("Your Name (VOSE)", ["17:50"], rating)],
    }
    lines = _global_top_lines(block, 10)
    text = "\n".join(lines)
    assert "Verdi" in text and "Maldà" in text
    assert "1." in text


def test_global_top_empty_when_no_ratings():
    block = {
        "Verdi": [("Solo sin nota", ["20:30"], None)],
    }
    assert _global_top_lines(block, 10) == []
