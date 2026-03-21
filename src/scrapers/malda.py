from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timedelta
from html import unescape
from typing import List, Optional, Set
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests

from models import Film, Show

from .base import BaseScraper

logger = logging.getLogger(__name__)

CARTELERA_DIA_URL = "https://www.cinemamalda.com/cartelera-dia-dia/"
BASE = "https://www.cinemamalda.com"

# Slugs que no son películas en cartelera
_EXCLUDE_PATH_PREFIXES: Set[str] = {
    "wp-",
    "tag",
    "category",
    "author",
    "page",
    "precios",
    "aviso-legal",
    "suscribirse",
    "cartelera-dia-dia",
}

# Slugs puntuales (legales / utilidades) enlazados desde la cartelera
_EXCLUDE_SLUGS: Set[str] = {
    "aviso-legal",
    "politica-de-cookies",
    "politica-de-privacidad",
    "suscribirse",
    "precios-cine-malda-barcelona-preus",
}

# Día semana en bloque SESIONES (lunes=0 … domingo=6)
_DOW_TOKEN: dict[str, int] = {
    "lu": 0,
    "ma": 1,
    "mi": 2,
    "ju": 3,
    "vi": 4,
    "sá": 5,
    "sa": 5,
    "do": 6,
}


def _norm_dow(tok: str) -> Optional[int]:
    t = tok.strip().lower()
    t = t.replace("á", "a")
    return _DOW_TOKEN.get(t[:2] if len(t) >= 2 else t)


def _resolve_show_date(dom: int, weekday_py: int, ref: date) -> Optional[date]:
    candidates: List[date] = []
    for delta in range(-2, 50):
        d = ref + timedelta(days=delta)
        if d.day == dom and d.weekday() == weekday_py:
            candidates.append(d)
    if not candidates:
        return None
    return min(candidates, key=lambda x: abs((x - ref).days))


def _parse_malda_sessions(text: str, ref: date) -> List[Show]:
    """Parsea bloque SESIONES con líneas tipo 'Sá 21' y '12:00h'."""
    shows: List[Show] = []
    low = text
    idx = low.upper().find("SESIONES")
    if idx < 0:
        return shows
    block = low[idx + len("SESIONES") :]
    for stop in ("TRAILER", "COMPRAR", "ENTRADAS"):
        p = block.upper().find(stop)
        if p >= 0:
            block = block[:p]
            break
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    i = 0
    while i < len(lines):
        m_d = re.match(
            r"^(Lu|Ma|Mi|Ju|Vi|Sá|Do|SA|Sa)\s+(\d{1,2})\s*$",
            lines[i],
            re.I,
        )
        if m_d and i + 1 < len(lines):
            wd = _norm_dow(m_d.group(1))
            dom = int(m_d.group(2))
            m_t = re.match(r"^(\d{1,2}):(\d{2})h\s*$", lines[i + 1], re.I)
            if wd is not None and m_t:
                sd = _resolve_show_date(dom, wd, ref)
                if sd:
                    hh = m_t.group(1).zfill(2)
                    mm = m_t.group(2)
                    dt_s = f"{sd.strftime('%Y%m%d')} {hh}:{mm}"
                    shows.append(Show(datetime=dt_s))
                i += 2
                continue
        i += 1
    return shows


class MaldaScraper(BaseScraper):
    cinema_name = "Maldà"

    def fetch(self) -> List[Film]:
        from bs4 import BeautifulSoup

        from utils import DEFAULT_HEADERS

        r = requests.get(CARTELERA_DIA_URL, headers=DEFAULT_HEADERS, timeout=25)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "lxml")
        film_urls: Set[str] = set()

        for a in soup.find_all("a", href=True):
            href = a["href"].split("#")[0].rstrip("/")
            if not href.startswith(BASE):
                continue
            path = urlparse(href).path.strip("/")
            if not path or "/" in path:
                continue
            seg = path.split("/")[0].lower()
            if any(seg.startswith(p) for p in _EXCLUDE_PATH_PREFIXES):
                continue
            if seg in ("cartelera-dia-dia", "precios-cine-malda-barcelona-preus"):
                continue
            if seg in _EXCLUDE_SLUGS:
                continue
            film_urls.add(href.rstrip("/") + "/")

        films: List[Film] = []
        tz = ZoneInfo("Europe/Madrid")
        ref_date = datetime.now(tz).date()

        for url in sorted(film_urls):
            try:
                time.sleep(0.35)
                fr = requests.get(url, headers=DEFAULT_HEADERS, timeout=25)
                fr.raise_for_status()
                psoup = BeautifulSoup(fr.content, "lxml")
                title_el = psoup.select_one("h1.entry-title") or psoup.select_one("h1")
                title = (
                    title_el.get_text(" ", strip=True)
                    if title_el
                    else url.rstrip("/").split("/")[-1]
                )
                title = unescape(re.sub(r"<[^>]+>", "", title)).strip()
                body = psoup.select_one(".entry-content") or psoup.select_one("article")
                text = body.get_text("\n", strip=True) if body else ""
                shows = _parse_malda_sessions(text, ref_date)
                films.append(
                    Film(
                        cinema=self.cinema_name,
                        title=title,
                        url=url,
                        source_section="cartelera-dia-dia",
                        shows=shows,
                        labels=[],
                    )
                )
            except Exception as e:
                logger.warning("Maldà: no se pudo leer %s: %s", url, e)

        logger.info("Maldà: %s películas (cartelera día a día)", len(films))
        return films
