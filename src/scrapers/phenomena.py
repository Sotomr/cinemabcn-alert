from __future__ import annotations

import logging
import os
from typing import List
from urllib.parse import urljoin

from models import Film

from .base import BaseScraper

logger = logging.getLogger(__name__)

# La web oficial ha cambiado varias veces; prioriza PHENOMENA_BASE_URL en .env
DEFAULT_URLS = (
    "https://www.phenomena.cat/cartelera/",
    "https://www.phenomena.cat/",
)


class PhenomenaScraper(BaseScraper):
    cinema_name = "Phenomena"

    def fetch(self) -> List[Film]:
        from utils import fetch_soup

        urls: List[str] = []
        env = os.getenv("PHENOMENA_BASE_URL")
        if env:
            urls.append(env.rstrip("/") + "/")
        urls.extend(u for u in DEFAULT_URLS if u not in urls)

        last_error: Exception | None = None
        for base in urls:
            try:
                soup = fetch_soup(base)
                films = _parse(soup, base)
                if films:
                    logger.info("Phenomena: %s películas (fuente %s)", len(films), base)
                    return films
                logger.warning("Phenomena: 0 títulos en %s; probando siguiente URL", base)
            except Exception as e:
                last_error = e
                logger.warning("Phenomena: fallo %s: %s", base, e)

        if last_error:
            logger.error(
                "Phenomena: no se pudo obtener cartelera. "
                "Configura PHENOMENA_BASE_URL con la URL vigente del cine. "
                "Último error: %s",
                last_error,
            )
        return []


def _parse(soup, base_url: str) -> List[Film]:
    seen: set[str] = set()
    out: List[Film] = []

    for sel in ("article.film", "article.pelicula", "div.film-item", "li.cartelera-item"):
        for node in soup.select(sel):
            a = node.find("a", href=True)
            if not a:
                continue
            title = a.get_text(" ", strip=True)
            href = a["href"].strip()
            if not title or len(title) < 2:
                continue
            url = href if href.startswith("http") else urljoin(base_url, href)
            if url in seen:
                continue
            seen.add(url)
            out.append(
                Film(
                    cinema="Phenomena",
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
        if not any(x in href for x in ("/pelicula/", "/film/", "/movie/", "/cine/")):
            continue
        if href.startswith("#") or "facebook.com" in href or "twitter.com" in href:
            continue
        title = a.get_text(" ", strip=True)
        if not title or len(title) < 3 or len(title) > 180:
            continue
        url = href if href.startswith("http") else urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)
        out.append(
            Film(
                cinema="Phenomena",
                title=title,
                url=url,
                source_section="cartelera",
                labels=[],
            )
        )

    return out
