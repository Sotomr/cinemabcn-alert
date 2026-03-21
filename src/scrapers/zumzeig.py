from __future__ import annotations

import logging
import os
import re
from typing import Dict, List
from urllib.parse import urljoin

from models import Film, Show

from .base import BaseScraper

logger = logging.getLogger(__name__)

# Calendario mensual con sesiones (rel=fecha en cada celda). La home ya no enlaza igual.
DEFAULT_URLS = (
    "https://www.zumzeigcine.coop/es/cine/calendari/",
    "https://zumzeigcine.coop/es/cine/calendari/",
    "https://www.zumzeigcine.coop/",
    "https://zumzeigcine.coop/",
)


class ZumzeigScraper(BaseScraper):
    cinema_name = "Zumzeig"

    def fetch(self) -> List[Film]:
        from utils import fetch_soup

        urls: List[str] = []
        env = os.getenv("ZUMZEIG_CARTELERA_URL")
        if env:
            urls.append(env.strip())
        urls.extend(u for u in DEFAULT_URLS if u not in urls)

        last_error: Exception | None = None
        for base in urls:
            try:
                soup = fetch_soup(base)
                films = _parse_calendar(soup, base)
                if films:
                    for f in films:
                        f.shows.sort(key=lambda s: s.datetime)
                    logger.info(
                        "Zumzeig: %s películas con sesiones (fuente %s)",
                        len(films),
                        base,
                    )
                    return films
                films = _parse_legacy(soup, base)
                if films:
                    logger.info(
                        "Zumzeig: %s películas sin horarios (fuente %s, fallback)",
                        len(films),
                        base,
                    )
                    return films
                logger.warning("Zumzeig: 0 títulos en %s; probando siguiente URL", base)
            except Exception as e:
                last_error = e
                logger.warning("Zumzeig: fallo %s: %s", base, e)

        if last_error:
            logger.error(
                "Zumzeig: no se pudo obtener cartelera. "
                "Configura ZUMZEIG_CARTELERA_URL (p. ej. …/es/cine/calendari/). "
                "Último error: %s",
                last_error,
            )
        return []


def _parse_calendar(soup, base_url: str) -> List[Film]:
    """
    Tabla calendario: td[rel=YYYY-MM-DD] y a.sessio con .hora / .film.
    Enlaces: /es/cine/films/… o /cinema/films/…
    """
    by_url: Dict[str, Film] = {}
    seen_show: Dict[str, set[str]] = {}

    for td in soup.select("td[rel]"):
        rel = (td.get("rel") or "").strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", rel):
            continue
        y, month, day = (int(x) for x in rel.split("-"))
        for a in td.select("a.sessio[href]"):
            href = (a.get("href") or "").strip()
            if "/cine/films/" not in href and "/cinema/films/" not in href:
                continue
            hora_el = a.select_one(".hora")
            film_el = a.select_one(".film")
            if hora_el is None or film_el is None:
                continue
            tm_raw = hora_el.get_text(strip=True)
            tm = re.sub(r"\*$", "", tm_raw).strip()
            m = re.match(r"^(\d{1,2}):(\d{2})$", tm)
            if not m:
                continue
            tm = f"{int(m.group(1)):02d}:{m.group(2)}"
            title = film_el.get_text(" ", strip=True)
            if not title or len(title) < 2:
                continue
            url = href if href.startswith("http") else urljoin(base_url, href)
            dt_s = f"{y:04d}{month:02d}{day:02d} {tm}"
            if url not in seen_show:
                seen_show[url] = set()
            if dt_s in seen_show[url]:
                continue
            seen_show[url].add(dt_s)
            show = Show(datetime=dt_s)
            if url not in by_url:
                by_url[url] = Film(
                    cinema="Zumzeig",
                    title=title,
                    url=url,
                    source_section="calendari",
                    labels=[],
                    shows=[show],
                )
            else:
                by_url[url].shows.append(show)
                if title and len(title) > len(by_url[url].title):
                    by_url[url].title = title

    return list(by_url.values())


def _parse_legacy(soup, base_url: str) -> List[Film]:
    """Home antigua: enlaces a fichas sin calendario embebido."""
    seen: set[str] = set()
    out: List[Film] = []

    for h in soup.select("h2 a, h3 a, article h2 a"):
        href = h.get("href") or ""
        title = h.get_text(" ", strip=True)
        if not title or len(title) < 2:
            continue
        if href.startswith("#") or not href:
            continue
        if not _is_film_path(href):
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
        if not _is_film_path(href) and not any(
            x in href for x in ("/film/", "/pelicula/", "/movie/", "/seance")
        ):
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


def _is_film_path(href: str) -> bool:
    return "/cinema/films/" in href or "/cine/films/" in href
