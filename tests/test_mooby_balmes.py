import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from models import Film

from scrapers.mooby_balmes import (
    _extract_shops_json,
    _find_balmes_shop,
    _film_url_for_event,
    _perf_to_show,
)


def test_extract_shops_json():
    html = """<script>
window.shops = {"29":{"id":29,"slug":"/balmes","events":[]}};
</script>"""
    shops = _extract_shops_json(html)
    assert shops is not None
    assert "29" in shops


def test_find_balmes_shop():
    shops = {
        "24": {"slug": "/arenas", "events": []},
        "29": {"slug": "/balmes", "events": []},
    }
    s = _find_balmes_shop(shops)
    assert s["slug"] == "/balmes"


def test_perf_to_show():
    s = _perf_to_show(
        {
            "time": "20260328222000",
            "hall_name": "SALA 08",
        }
    )
    assert s is not None
    assert s.datetime == "20260328 22:20"
    assert s.room == "SALA 08"


def test_film_url_for_event():
    assert _film_url_for_event({"imdbid": "tt1234567"}, "https://x") == (
        "https://www.imdb.com/title/tt1234567/"
    )
    assert _film_url_for_event({}, "https://www.moobycinemas.com/balmes") == (
        "https://www.moobycinemas.com/balmes"
    )


def test_parse_minimal_embedded_shop():
    html = """<script>
window.shops = {"29":{"id":29,"slug":"/balmes","events":[
  {"locale_title":"Test (VOSE)","imdbid":"tt1234567","performances":[
    {"time":"20260328180000","hall_name":"SALA 01"}
  ]}
]}};
</script>"""
    shops = _extract_shops_json(html)
    shop = _find_balmes_shop(shops or {})
    ev = shop["events"][0]
    shows = [_perf_to_show(p) for p in ev["performances"]]
    f = Film(
        cinema="Mooby Balmes",
        title=ev["locale_title"],
        url=_film_url_for_event(ev, "https://www.moobycinemas.com/balmes"),
        source_section="t",
        shows=[s for s in shows if s],
    )
    assert f.shows[0].datetime == "20260328 18:00"
