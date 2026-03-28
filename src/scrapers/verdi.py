from __future__ import annotations

import logging
import re
import time
from typing import Dict, List
from urllib.parse import urljoin

from models import Film, Show

from .base import BaseScraper

logger = logging.getLogger(__name__)

CARTELERA_URLS = (
    "https://barcelona.cines-verdi.com/cartellera",
    "https://barcelona.cines-verdi.com/cartelera",
)
BASE = "https://barcelona.cines-verdi.com"

_MONTH_MAP: Dict[str, int] = {
    "gener": 1, "enero": 1, "january": 1,
    "febrer": 2, "febrero": 2, "february": 2,
    "març": 3, "marzo": 3, "march": 3,
    "abril": 4, "april": 4,
    "maig": 5, "mayo": 5, "may": 5,
    "juny": 6, "junio": 6, "june": 6,
    "juliol": 7, "julio": 7, "july": 7,
    "agost": 8, "agosto": 8, "august": 8,
    "setembre": 9, "septiembre": 9, "september": 9,
    "octubre": 10, "october": 10,
    "novembre": 11, "noviembre": 11, "november": 11,
    "desembre": 12, "diciembre": 12, "december": 12,
}


class VerdiScraper(BaseScraper):
    cinema_name = "Verdi"

    def fetch(self) -> List[Film]:
        from utils import fetch_soup

        soup = None
        for url in CARTELERA_URLS:
            try:
                soup = fetch_soup(url)
                if soup.select(".info-cartelera-performances"):
                    break
            except Exception:
                continue

        if soup is None:
            raise RuntimeError("No se pudo acceder a la cartelera de Verdi")

        film_stubs = _parse_cartelera(soup)
        if not film_stubs:
            logger.warning("Verdi: 0 títulos en cartelera")
            return []

        films: List[Film] = []
        for title, path in film_stubs:
            detail_url = path if path.startswith("http") else urljoin(BASE, path)
            try:
                detail_soup = fetch_soup(detail_url, timeout=15, retries=1)
                shows, lang_suffix = _parse_detail_shows(detail_soup)
            except Exception as e:
                logger.warning("Verdi detalle %s: %s", detail_url, e)
                shows, lang_suffix = [], ""
            display_title = f"{title} {lang_suffix}".strip() if lang_suffix else title
            films.append(
                Film(
                    cinema="Verdi",
                    title=display_title,
                    url=detail_url,
                    source_section="cartelera",
                    shows=shows,
                    labels=[],
                )
            )
            time.sleep(0.08)

        logger.info("Verdi: %s películas", len(films))
        return films


def _parse_cartelera(soup) -> List[tuple[str, str]]:
    """Extrae (título, path relativo) de la cartelera."""
    out: List[tuple[str, str]] = []
    seen: set[str] = set()
    for div in soup.select(".info-cartelera-performances"):
        h2 = div.select_one("h2")
        if not h2:
            continue
        title = h2.get_text(" ", strip=True)
        if not title or len(title) < 2:
            continue
        link = div.select_one("a[href]")
        if not link:
            continue
        href = (link.get("href") or "").strip()
        if not href or href.startswith("#"):
            continue
        if href in seen:
            continue
        seen.add(href)
        out.append((title, href))
    return out


def _parse_detail_shows(soup) -> tuple[List[Show], str]:
    """
    Pàgina de detall: section.performances-vert conté divs alternats amb
    <time><strong>DD DE MES</strong><small>YYYY</small></time>
    i un <a x-show="!isPast('YYYYMMDDHHMMSS')"> amb <time>HH:MM</time>.
    Retorna les sessions i un sufijo de idioma (VOSE, etc.) si és comú.
    """
    shows: List[Show] = []
    langs: set[str] = set()

    section = soup.select_one("section.performances-vert")
    if not section:
        return _parse_detail_shows_xshow(soup)

    current_date: str | None = None
    for div in section.select("div"):
        time_el = div.select_one("time")
        if not time_el:
            continue
        strong = time_el.select_one("strong")
        small = time_el.select_one("small")
        if strong and small:
            raw_date = strong.get_text(strip=True)
            raw_year = small.get_text(strip=True)
            parsed = _parse_catalan_date(raw_date, raw_year)
            if parsed:
                current_date = parsed
            continue
        a = div.select_one("a[x-show]")
        if a is None:
            a = div.select_one("a[href]")
        if a and current_date:
            tm_el = a.select_one("time")
            if tm_el:
                hm = tm_el.get_text(strip=True)
                m = re.match(r"^(\d{1,2}):(\d{2})$", hm)
                if m:
                    hm_fmt = f"{int(m.group(1)):02d}:{m.group(2)}"
                    shows.append(Show(datetime=f"{current_date} {hm_fmt}"))
            lang_el = a.select_one("small")
            if lang_el:
                lt = lang_el.get_text(strip=True).upper()
                if "V.O" in lt or "VOSE" in lt or "VOSC" in lt:
                    langs.add("VOSE")

    lang_suffix = "VOSE" if langs and len(langs) == 1 else ""
    return shows, lang_suffix


def _parse_detail_shows_xshow(soup) -> tuple[List[Show], str]:
    """Fallback: busca tots els <a x-show="!isPast('...')">."""
    shows: List[Show] = []
    for a in soup.select("a[x-show]"):
        xs = a.get("x-show") or ""
        m = re.search(r"isPast\(['\"](\d{8})(\d{6})['\"]", xs)
        if m:
            date_s = m.group(1)
            time_s = m.group(2)
            hm = f"{time_s[:2]}:{time_s[2:4]}"
            shows.append(Show(datetime=f"{date_s} {hm}"))
    return shows, ""


def _parse_catalan_date(raw_date: str, raw_year: str) -> str | None:
    """'28 DE MARÇ' + '2026' -> '20260328'."""
    m = re.match(r"(\d{1,2})\s+DE\s+(\w+)", raw_date, re.I)
    if not m:
        return None
    day = int(m.group(1))
    month_name = m.group(2).lower()
    month = _MONTH_MAP.get(month_name)
    if month is None:
        return None
    try:
        year = int(raw_year.strip())
    except ValueError:
        return None
    return f"{year:04d}{month:02d}{day:02d}"
