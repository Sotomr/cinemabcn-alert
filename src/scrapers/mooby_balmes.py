from __future__ import annotations

import logging
from typing import List
from urllib.parse import urljoin

from models import Film

from .base import BaseScraper

logger = logging.getLogger(__name__)

# Mooby Cinemas — Balmes (la ficha no publica horas en HTML estático)
CARTELERA_URL = "https://www.moobycinemas.com/wai/balmes"
BASE = "https://www.moobycinemas.com"


class MoobyBalmesScraper(BaseScraper):
    cinema_name = "Moby Balmes"

    def fetch(self) -> List[Film]:
        from utils import fetch_soup

        soup = fetch_soup(CARTELERA_URL)
        films: List[Film] = []
        seen: set[str] = set()

        for a in soup.select("nav#cartelera a[href]"):
            href = (a.get("href") or "").strip()
            if not href.startswith("/wai/"):
                continue
            title = a.get_text(" ", strip=True)
            if not title or len(title) < 2:
                continue
            url = href if href.startswith("http") else urljoin(BASE, href)
            if url in seen:
                continue
            seen.add(url)
            films.append(
                Film(
                    cinema=self.cinema_name,
                    title=title,
                    url=url,
                    source_section="cartelera",
                    labels=[],
                )
            )

        logger.info("Moby Balmes: %s entradas en cartelera (sin horas en HTML)", len(films))
        return films
