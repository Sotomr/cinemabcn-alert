import sys
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from digest import (
    DigestLimits,
    _global_top_lines,
    build_digest_telegram_parts,
    parse_show_date,
    parse_show_time,
    score_from_rating_html,
    two_calendar_days,
)
from models import Film, Show


def test_parse_verdi_show():
    s = Show(datetime="20260321 20:30")
    assert parse_show_date(s) == date(2026, 3, 21)
    assert parse_show_time(s) == "20:30"


def test_score_from_rating_html():
    assert score_from_rating_html("★ 7.5 TMDb IMDb") == 7.5
    assert score_from_rating_html(None) == -1.0
    assert score_from_rating_html("") == -1.0


def test_global_top_merges_same_film_across_cinemas():
    rating = "★ 8.5 TMDb IMDb"
    block = {
        "Verdi": [("Your name VOSE", ["20:30"], rating)],
        "Maldà": [("Your Name (VOSE)", ["17:50"], rating)],
    }
    lines = _global_top_lines(block, 10)
    text = "\n".join(lines)
    assert "Verdi" in text and "Maldà" in text
    assert "   1." in text
    assert "   2." not in text


def test_global_top_empty_when_no_ratings():
    block = {
        "Verdi": [("Solo sin nota", ["20:30"], None)],
    }
    assert _global_top_lines(block, 10) == []


def test_build_digest_telegram_parts_top_and_schedules():
    tz = ZoneInfo("Europe/Madrid")
    d0, _ = two_calendar_days(tz)
    dt = f"{d0.strftime('%Y%m%d')} 20:00"
    films = [
        Film(
            cinema="Alpha",
            title="Pel A",
            url="https://x/a",
            source_section="t",
            shows=[Show(datetime=dt)],
            rating="★ 8.0 IMDb",
        ),
        Film(
            cinema="Beta",
            title="Pel B",
            url="https://x/b",
            source_section="t",
            shows=[Show(datetime=dt)],
            rating="★ 7.5 IMDb",
        ),
    ]
    parts = build_digest_telegram_parts(
        films,
        [],
        tz_name="Europe/Madrid",
        limits=DigestLimits(global_top_per_day=10),
    )
    assert len(parts) == 2
    assert "Cartellera" in parts[0]
    assert "pel a" in parts[0]
    assert "pel b" in parts[0]
    assert "Horaris" in parts[1]
    assert "Alpha" in parts[1]
    assert "Beta" in parts[1]
