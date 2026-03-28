from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from models import Film, Show

from .base import BaseScraper

logger = logging.getLogger(__name__)

CARTELERA_URL = "https://www.cinesrenoir.com/cine/renoir-floridablanca/cartelera/"
BASE = "https://www.cinesrenoir.com"

_ES_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def _parse_day_from_header(soup) -> Optional[str]:
    """Extract YYYYMMDD from 'Pases de Renoir Floridablanca para el Sábado 28 Marzo'."""
    for h5 in soup.select("h5"):
        text = h5.get_text(strip=True)
        m = re.search(r"(\d{1,2})\s+(\w+)\s*$", text)
        if not m:
            continue
        day = int(m.group(1))
        month_name = m.group(2).lower()
        month = _ES_MONTHS.get(month_name)
        if not month:
            continue
        year = datetime.now(ZoneInfo("Europe/Madrid")).year
        try:
            d = date(year, month, day)
            return d.strftime("%Y%m%d")
        except ValueError:
            continue
    return None


class RenoirScraper(BaseScraper):
    cinema_name = "Renoir Floridablanca"

    def fetch(self) -> List[Film]:
        from utils import fetch_soup

        soup = fetch_soup(CARTELERA_URL)
        date_str = _parse_day_from_header(soup)
        if not date_str:
            today = datetime.now(ZoneInfo("Europe/Madrid")).date()
            date_str = today.strftime("%Y%m%d")
            logger.warning("Renoir: no se pudo parsear la fecha; usando hoy %s", date_str)

        films: List[Film] = []
        seen: dict[str, Film] = {}

        for block in soup.select(".my-account-content"):
            title_a = block.select_one("a[href*=pelicula]")
            if not title_a:
                continue
            raw_title = title_a.get_text(strip=True)
            if not raw_title or len(raw_title) < 2:
                continue
            title = raw_title.strip().title()
            href = title_a.get("href", "")
            url = f"{BASE}{href}" if href and not href.startswith("http") else href

            version_text = block.get_text(" ", strip=True)
            is_vo = bool(re.search(r"Versi[oó]n\s+Original", version_text, re.I))
            if is_vo:
                lang_m = re.search(
                    r"Versi[oó]n\s+Original\s+(\w+)", version_text, re.I
                )
                lang = lang_m.group(1) if lang_m else "VO"
            else:
                lang = None

            shows: List[Show] = []
            for pase in block.select(".pase-cartelera"):
                text = pase.get_text(" ", strip=True)
                time_m = re.search(r"(\d{2}):(\d{2})", text)
                if time_m:
                    hh, mm = time_m.group(1), time_m.group(2)
                    shows.append(
                        Show(
                            datetime=f"{date_str} {hh}:{mm}",
                            language=lang,
                        )
                    )

            norm = title.strip().lower()
            if norm in seen:
                existing = seen[norm]
                existing_dts = {s.datetime for s in existing.shows}
                for s in shows:
                    if s.datetime not in existing_dts:
                        existing.shows.append(s)
                continue

            film = Film(
                cinema=self.cinema_name,
                title=title,
                url=url,
                source_section="cartelera",
                shows=shows,
                labels=[],
            )
            films.append(film)
            seen[norm] = film

        logger.info("Renoir Floridablanca: %s películas", len(films))
        return films
