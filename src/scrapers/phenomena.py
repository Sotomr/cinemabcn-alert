from __future__ import annotations

import logging
import os
import re
from datetime import date
from typing import List
from urllib.parse import urljoin

from models import Film, Show

from .base import BaseScraper

logger = logging.getLogger(__name__)


def _ensure_scheme(url: str) -> str:
    url = url.strip()
    if not url.startswith("http"):
        return "https://" + url
    return url


# Sitio actual (2025–2026): programación en phenomena-experience.com
DEFAULT_URLS = (
    "https://phenomena-experience.com/index?pag=cartelera",
    "https://www.phenomena.cat/cartelera/",
    "https://www.phenomena.cat/",
)

_DATE_DMY = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_TIME_H = re.compile(r"^(\d{1,2}):(\d{2})\s*h?\s*$", re.I)


def _parse_shows_from_block(block) -> List[Show]:
    """Sesiones en .lista-sesiones: .fch-format (DD/MM/YYYY) + .sesiones-dia horas."""
    shows: List[Show] = []
    lista = block.select_one(".lista-sesiones")
    if not lista:
        return shows

    current: date | None = None
    for node in lista.children:
        if getattr(node, "name", None) is None:
            continue
        cls = node.get("class") or []
        if "fch-format" in cls:
            txt = node.get_text(strip=True)
            m = _DATE_DMY.match(txt)
            if m:
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                try:
                    current = date(y, mo, d)
                except ValueError:
                    current = None
            continue
        if "sesiones-dia" not in cls or current is None:
            continue
        for ses in node.select(".grupo.cont-ses div"):
            raw = ses.get_text(strip=True)
            tm = _TIME_H.match(raw.replace("h", "").strip())
            if not tm:
                continue
            hh = tm.group(1).zfill(2)
            mm = tm.group(2)
            shows.append(Show(datetime=f"{current.strftime('%Y%m%d')} {hh}:{mm}"))
    return shows


def _parse_experience_cartelera(soup, base_url: str) -> List[Film]:
    out: List[Film] = []
    seen: set[str] = set()

    for block in soup.select("div.cartelera.bloque50"):
        tit_el = block.select_one(".cartelera-titulo")
        if not tit_el:
            continue
        title = tit_el.get_text(" ", strip=True)
        if not title or len(title) < 2:
            continue

        a = block.select_one(".cartelera-imagen a[href]") or block.select_one(
            "a[href*='pag=ficha']"
        )
        url = ""
        if a and a.get("href"):
            href = a["href"].strip()
            url = href if href.startswith("http") else urljoin(base_url, href)

        shows = _parse_shows_from_block(block)
        key = url or title.lower()
        if key in seen:
            continue
        seen.add(key)

        out.append(
            Film(
                cinema="Phenomena",
                title=title,
                url=url,
                source_section="cartelera",
                shows=shows,
                labels=[],
            )
        )
    return out


def _parse_legacy_links(soup, base_url: str) -> List[Film]:
    """Fallback si cambia el HTML (solo títulos + enlaces)."""
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
        if not any(x in href for x in ("/pelicula/", "/film/", "/movie/", "/cine/", "pag=ficha")):
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


class PhenomenaScraper(BaseScraper):
    cinema_name = "Phenomena"

    def fetch(self) -> List[Film]:
        from utils import fetch_soup

        urls: List[str] = []
        env = os.getenv("PHENOMENA_BASE_URL")
        if env:
            urls.append(env.strip().rstrip("/"))
        urls.extend(u for u in DEFAULT_URLS if u not in urls)

        last_error: Exception | None = None
        for base in urls:
            try:
                base = _ensure_scheme(base)
                soup = fetch_soup(base)
                films = _parse_experience_cartelera(soup, base)
                if films:
                    with_shows = sum(1 for f in films if f.shows)
                    logger.info(
                        "Phenomena: %s películas (%s con sesiones) — %s",
                        len(films),
                        with_shows,
                        base,
                    )
                    return films
                legacy = _parse_legacy_links(soup, base)
                if legacy:
                    logger.info(
                        "Phenomena: %s películas (sin bloques cartelera; solo enlaces) — %s",
                        len(legacy),
                        base,
                    )
                    return legacy
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
