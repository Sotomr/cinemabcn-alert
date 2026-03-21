from __future__ import annotations

import logging
from typing import List

from models import Film

from .base import BaseScraper

logger = logging.getLogger(__name__)

CARTELLERA_URL = "https://espaitexas.cat/cartellera-cinema/"


class EspaiTexasScraper(BaseScraper):
    cinema_name = "Espai Texas"

    def fetch(self) -> List[Film]:
        from utils import fetch_soup

        soup = fetch_soup(CARTELLERA_URL)
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

        logger.info("Espai Texas: %s películas", len(films))
        return films
