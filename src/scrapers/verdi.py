from __future__ import annotations

import logging
import re
from typing import List
from urllib.parse import urljoin

from models import Film, Show

from .base import BaseScraper

logger = logging.getLogger(__name__)

CARTELERA_URL = "https://barcelona.cines-verdi.com/es/cartelera"
BASE = "https://barcelona.cines-verdi.com"


class VerdiScraper(BaseScraper):
    cinema_name = "Verdi"

    def fetch(self) -> List[Film]:
        from utils import fetch_soup

        soup = fetch_soup(CARTELERA_URL)
        films: List[Film] = []

        for art in soup.select("article.article-cartelera"):
            h2 = art.find("h2")
            if not h2:
                continue
            a = h2.find("a", href=True)
            if not a:
                continue
            title = a.get_text(" ", strip=True)
            if not title:
                continue
            path = a["href"].strip()
            url = path if path.startswith("http") else urljoin(BASE, path)

            labels: List[str] = []
            av = art.select_one(".avisocartel span")
            if av:
                labels.append(av.get_text(strip=True))

            shows: List[Show] = []
            for slot in art.select("a.mr-1.mb-1[title]"):
                t = (slot.get("title") or "").strip()
                m = re.search(r"(\d{8})\s+(\d{2}:\d{2})", t)
                if m:
                    shows.append(Show(datetime=f"{m.group(1)} {m.group(2)}"))

            films.append(
                Film(
                    cinema=self.cinema_name,
                    title=title,
                    url=url,
                    source_section="cartelera",
                    shows=shows,
                    labels=labels,
                )
            )

        logger.info("Verdi: %s películas", len(films))
        return films
