import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from scrapers.espai_texas import _parse_texas_sessions
from bs4 import BeautifulSoup


def test_parse_texas_sessions_from_html_snippet():
    html = """
    <div class="session">
      <div class="session-time font-small">21/03/26</div>
      <div class="session-time">20:30</div>
      <div class="session-time font-epigrafe color-black">20:30</div>
    </div>
    """
    soup = BeautifulSoup(html, "lxml")
    shows = _parse_texas_sessions(soup)
    assert len(shows) == 1
    assert shows[0].datetime == "20260321 20:30"
