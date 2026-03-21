import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bs4 import BeautifulSoup

from scrapers.zumzeig import _parse_calendar


def test_calendar_extracts_show_datetime():
    html = """
    <table>
    <tr><td rel="2026-03-21" class="day">
    <a href="/es/cine/films/little-amelie/" class="sessio">
      <div class="hora">17:00</div><div class="film">Little Amélie</div>
    </a>
    <a href="/es/cine/films/el-agente-secreto/" class="sessio">
      <div class="hora">19:00*</div><div class="film">El agente secreto</div>
    </a>
    </td></tr>
    </table>
    """
    films = _parse_calendar(
        BeautifulSoup(html, "lxml"),
        "https://www.zumzeigcine.coop/es/cine/calendari/",
    )
    assert len(films) == 2
    by_url = {f.url.split("/")[-2]: f for f in films}
    assert by_url["little-amelie"].shows[0].datetime == "20260321 17:00"
    assert by_url["el-agente-secreto"].shows[0].datetime == "20260321 19:00"


def test_legacy_accepts_es_cine_films_path():
    from scrapers.zumzeig import _is_film_path

    assert _is_film_path("/es/cine/films/foo/")
    assert _is_film_path("/cinema/films/foo/")
