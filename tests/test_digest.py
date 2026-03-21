import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from digest import parse_show_date, parse_show_time
from models import Show


def test_parse_verdi_show():
    s = Show(datetime="20260321 20:30")
    assert parse_show_date(s) == date(2026, 3, 21)
    assert parse_show_time(s) == "20:30"
