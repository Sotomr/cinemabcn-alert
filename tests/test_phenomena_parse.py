import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bs4 import BeautifulSoup

from scrapers.phenomena import _parse_experience_cartelera, _parse_shows_from_block


def test_parse_shows_from_block_snippet():
    html = """
    <div class="cartelera bloque50">
      <div class="lista-sesiones">
        <div class="fch-format">21/03/2026</div>
        <div class="sesiones-dia">
          <div class="grupo cont-ses"><div>18:30h</div></div>
          <div class="grupo cont-ses"><div>22:00h</div></div>
        </div>
      </div>
    </div>
    """
    soup = BeautifulSoup(html, "lxml")
    block = soup.select_one("div.cartelera")
    shows = _parse_shows_from_block(block)
    assert len(shows) == 2
    assert shows[0].datetime == "20260321 18:30"
    assert shows[1].datetime == "20260321 22:00"


def test_parse_experience_cartelera_minimal():
    html = """
    <div class="cartelera bloque50">
      <div class="cartelera-titulo"><b><div>TEST FILM</div></b></div>
      <div class="cartelera-imagen"><p><a href="https://phenomena-experience.com/index?pag=ficha&evento=1">x</a></p></div>
      <div class="lista-sesiones">
        <div class="fch-format">22/03/2026</div>
        <div class="sesiones-dia">
          <div class="grupo cont-ses"><div>20:00h</div></div>
        </div>
      </div>
    </div>
    """
    soup = BeautifulSoup(html, "lxml")
    films = _parse_experience_cartelera(soup, "https://phenomena-experience.com/index?pag=cartelera")
    assert len(films) == 1
    assert films[0].title == "TEST FILM"
    assert films[0].shows[0].datetime == "20260322 20:00"
