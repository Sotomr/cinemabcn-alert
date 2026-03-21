from __future__ import annotations

import logging
import re
import time
from datetime import date
from typing import List

import requests
from bs4 import BeautifulSoup

from models import Film, Show

from .base import BaseScraper

logger = logging.getLogger(__name__)

CARTELLERA_URL = "https://espaitexas.cat/cartellera-cinema/"

_DATE_DDMMYY = re.compile(r"^(\d{2})/(\d{2})/(\d{2})$")
_TIME_HHMM = re.compile(r"^(\d{2}):(\d{2})$")


def _parse_texas_sessions(soup: BeautifulSoup) -> List[Show]:
    """
    Horarios en bloques .session: fecha en .session-time.font-small (DD/MM/AA)
    y hora en .session-time con formato HH:MM (puede repetirse).
    """
    shows: List[Show] = []
    for block in soup.select(".session"):
        small = block.select_one(".session-time.font-small")
        if not small:
            continue
        dm = _DATE_DDMMYY.match(small.get_text(strip=True))
        if not dm:
            continue
        dd, mm, yy = (int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
        year = 2000 + yy
        try:
            d = date(year, mm, dd)
        except ValueError:
            continue

        bottom_txt = ""
        btm = block.select_one(".session-bottom")
        if btm:
            bottom_txt = btm.get_text(" ", strip=True).lower()

        times: List[str] = []
        for el in block.select(".session-time"):
            t = el.get_text(strip=True)
            if not _TIME_HHMM.match(t):
                continue
            if t == "00:00" and "pròximament" in bottom_txt:
                continue
            times.append(t)

        for tm in sorted(set(times)):
            if tm == "00:00":
                continue
            shows.append(Show(datetime=f"{d.strftime('%Y%m%d')} {tm}"))
    return shows


class EspaiTexasScraper(BaseScraper):
    cinema_name = "Espai Texas"

    def fetch(self) -> List[Film]:
        from utils import DEFAULT_HEADERS

        r = requests.get(CARTELLERA_URL, headers=DEFAULT_HEADERS, timeout=25)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "lxml")
        films: List[Film] = []

        for h2 in soup.select("h2.title.color-green"):
            a = h2.find("a", href=True)
            if not a:
                continue
            title = a.get_text(" ", strip=True)
            if not title:
                continue
            url = a["href"].strip()
            films.append(
                Film(
                    cinema=self.cinema_name,
                    title=title,
                    url=url,
                    source_section="cartellera-cinema",
                    labels=[],
                )
            )

        for i, film in enumerate(films):
            if i:
                time.sleep(0.35)
            try:
                fr = requests.get(film.url, headers=DEFAULT_HEADERS, timeout=25)
                fr.raise_for_status()
                psoup = BeautifulSoup(fr.content, "lxml")
                film.shows = _parse_texas_sessions(psoup)
            except Exception as e:
                logger.warning("Espai Texas: no sesiones %s: %s", film.title, e)

        logger.info("Espai Texas: %s películas", len(films))
        return films
