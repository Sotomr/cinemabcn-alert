from __future__ import annotations

import logging
import os
from typing import List
from urllib.parse import urljoin

from models import Film

from .base import BaseScraper

logger = logging.getLogger(__name__)

# Cooperativa Zumzeig (Barcelona): la URL pública a veces cambia; usa ZUMZEIG_CARTELERA_URL si falla.
DEFAULT_URLS = (
    "https://www.zumzeig.fr/",
    "https://zumzeig.org/",
    "https://www.zumzeig.org/",
)


class ZumzeigScraper(BaseScraper):
    cinema_name = "Zumzeig"

    def fetch(self) -> List[Film]:
        from utils import fetch_soup

        urls: List[str] = []
        env = os.getenv("ZUMZEIG_CARTELERA_URL")
        if env:
            urls.append(env)
        urls.extend(u for u in DEFAULT_URLS if u not in urls)

        last_error: Exception | None = None
        for base in urls:
            try:
                soup = fetch_soup(base)
                films = _parse(soup, base)
                if films:
                    logger.info("Zumzeig: %s películas (fuente %s)", len(films), base)
                    return films
                logger.warning("Zumzeig: 0 títulos en %s; probando siguiente URL", base)
            except Exception as e:
                last_error = e
                logger.warning("Zumzeig: fallo %s: %s", base, e)

        if last_error:
            logger.error(
                "Zumzeig: no se pudo obtener cartelera. "
                "Configura ZUMZEIG_CARTELERA_URL con la página de programación actual. "
                "Último error: %s",
                last_error,
            )
        return []


def _parse(soup, base_url: str) -> List[Film]:
    seen: set[str] = set()
    out: List[Film] = []

    for h in soup.select("h2 a, h3 a, article h2 a"):
        href = h.get("href") or ""
        title = h.get_text(" ", strip=True)
        if not title or len(title) < 2:
            continue
        if href.startswith("#") or not href:
            continue
        url = href if href.startswith("http") else urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)
        out.append(
            Film(
                cinema="Zumzeig",
                title=title,
                url=url,
                source_section="cartelera",
                labels=[],
            )
        )

    if out:
        return out

    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        if not any(x in href for x in ("/film/", "/films/", "/pelicula/", "/movie/", "/seance")):
            continue
        title = a.get_text(" ", strip=True)
        if not title or len(title) < 3:
            continue
        url = href if href.startswith("http") else urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)
        out.append(
            Film(
                cinema="Zumzeig",
                title=title,
                url=url,
                source_section="cartelera",
                labels=[],
            )
        )

    return out
