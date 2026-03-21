from __future__ import annotations

import logging
import re
from html import unescape
from typing import List, Set

import requests

from models import Film

from .base import BaseScraper

logger = logging.getLogger(__name__)

API = "https://www.cinemamalda.com/wp-json/wp/v2/posts"
CATEGORY_PELICULAS = 3

# Páginas informativas que a veces comparten la categoría "Peliculas"
_EXCLUDE_SLUGS: Set[str] = {
    "cartelera-dia-dia",
    "precios-cine-malda-barcelona-preus",
}

_EXCLUDE_TITLE_RES = (
    re.compile(r"^cartelera\s+d[ií]a\s+a\s+d[ií]a", re.I),
    re.compile(r"^precios\b", re.I),
)


class MaldaScraper(BaseScraper):
    cinema_name = "Maldà"

    def fetch(self) -> List[Film]:
        films: List[Film] = []
        page = 1
        while page <= 5:
            r = requests.get(
                API,
                params={
                    "categories": CATEGORY_PELICULAS,
                    "per_page": 100,
                    "page": page,
                    "_fields": "title,link,slug",
                },
                timeout=25,
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            for p in batch:
                slug = p.get("slug") or ""
                if slug in _EXCLUDE_SLUGS:
                    continue
                title = unescape((p.get("title") or {}).get("rendered") or "").strip()
                title = re.sub(r"<[^>]+>", "", title).strip()
                if not title:
                    continue
                if any(rx.match(title) for rx in _EXCLUDE_TITLE_RES):
                    continue
                link = p.get("link") or ""
                films.append(
                    Film(
                        cinema=self.cinema_name,
                        title=title,
                        url=link,
                        source_section="wp:peliculas",
                        labels=[],
                    )
                )
            if len(batch) < 100:
                break
            page += 1

        logger.info("Maldà: %s entradas", len(films))
        return films
