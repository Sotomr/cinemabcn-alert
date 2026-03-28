from __future__ import annotations

import logging
import re
from typing import List, Optional
from urllib.parse import urljoin

from models import Film, Show

from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.filmoteca.cat"
AGENDA_URL = f"{BASE_URL}/web/ca/view-agenda-setmanal"

_CATALAN_DAYS = {
    "dilluns": 0,
    "dimarts": 1,
    "dimecres": 2,
    "dijous": 3,
    "divendres": 4,
    "dissabte": 5,
    "diumenge": 6,
}

_CATALAN_MONTHS = {
    "gener": 1, "febrer": 2, "març": 3, "abril": 4,
    "maig": 5, "juny": 6, "juliol": 7, "agost": 8,
    "setembre": 9, "octubre": 10, "novembre": 11, "desembre": 12,
}


def _current_year_month() -> tuple[int, int]:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Europe/Madrid"))
    return now.year, now.month


def _resolve_day(day_num: int) -> str:
    """Given just a day-of-month from the weekly agenda, resolve YYYYMMDD."""
    from datetime import date, timedelta

    year, month = _current_year_month()
    today = date.today()
    for delta in range(-3, 10):
        d = today + timedelta(days=delta)
        if d.day == day_num:
            return d.strftime("%Y%m%d")
    try:
        return date(year, month, day_num).strftime("%Y%m%d")
    except ValueError:
        next_m = month + 1 if month < 12 else 1
        next_y = year if month < 12 else year + 1
        try:
            return date(next_y, next_m, day_num).strftime("%Y%m%d")
        except ValueError:
            return ""


class FilmotecaScraper(BaseScraper):
    cinema_name = "Filmoteca"

    def fetch(self) -> List[Film]:
        from utils import fetch_soup

        soup = fetch_soup(AGENDA_URL)
        films: List[Film] = []

        for block in soup.select(".block-day"):
            h2 = block.select_one("h2")
            if not h2:
                continue
            h2_text = h2.get_text(strip=True)
            m = re.search(r"(\d{1,2})", h2_text)
            if not m:
                continue
            day_num = int(m.group(1))
            date_str = _resolve_day(day_num)
            if not date_str:
                continue

            for card in block.select(".card"):
                hora_el = card.select_one(".hour, .hora")
                hora_text = hora_el.get_text(strip=True) if hora_el else ""
                time_m = re.search(r"(\d{1,2}):(\d{2})", hora_text)

                title_el = card.select_one(".titl a") or card.select_one(".titl")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if not title or len(title) < 2:
                    continue

                href = ""
                if title_el.name == "a" and title_el.get("href"):
                    href = urljoin(BASE_URL, title_el["href"])

                subtitle_el = card.select_one(".description.mini_text-1")
                original_title = subtitle_el.get_text(strip=True) if subtitle_el else ""

                director_year = ""
                more_info = card.select(".more-info .description.mini_text-1")
                if more_info:
                    director_year = more_info[0].get_text(strip=True)

                cycle_el = card.select_one(".text-alternatius a") or card.select_one(
                    ".text-alternatius"
                )
                cycle = cycle_el.get_text(strip=True) if cycle_el else ""

                display_title = title
                if original_title and original_title.lower() != title.lower():
                    display_title = f"{title} ({original_title})"

                labels: List[str] = []
                if cycle:
                    labels.append(cycle)
                if director_year:
                    labels.append(director_year)

                shows: List[Show] = []
                if time_m:
                    hh = time_m.group(1).zfill(2)
                    mm = time_m.group(2)
                    shows.append(Show(datetime=f"{date_str} {hh}:{mm}"))

                films.append(
                    Film(
                        cinema=self.cinema_name,
                        title=display_title,
                        url=href,
                        source_section="agenda-setmanal",
                        shows=shows,
                        labels=labels,
                    )
                )

        logger.info("Filmoteca: %s películas", len(films))
        return films
