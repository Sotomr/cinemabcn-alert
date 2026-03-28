from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from models import Film, Show

from .base import BaseScraper

logger = logging.getLogger(__name__)

DEFAULT_URL = "https://www.moobycinemas.com/balmes"


def _extract_shops_json(html: str) -> Optional[Dict[str, Any]]:
    marker = "window.shops = "
    start = html.find(marker)
    if start < 0:
        return None
    start += len(marker)
    depth = 0
    i = start
    while i < len(html):
        c = html[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start : i + 1])
                except json.JSONDecodeError:
                    return None
        i += 1
    return None


def _find_balmes_shop(shops: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for _sid, shop in shops.items():
        if not isinstance(shop, dict):
            continue
        slug = (shop.get("slug") or "").strip().rstrip("/").lower()
        if slug.endswith("balmes"):
            return shop
    return None


def _perf_to_show(perf: Dict[str, Any]) -> Optional[Show]:
    raw = (perf.get("time") or "").strip()
    if len(raw) < 14 or not raw.isdigit():
        return None
    ymd = raw[:8]
    hh, mm = raw[8:10], raw[10:12]
    return Show(datetime=f"{ymd} {hh}:{mm}", room=perf.get("hall_name"))


def _film_url_for_event(ev: Dict[str, Any], base: str) -> str:
    imdb = (ev.get("imdbid") or "").strip()
    if imdb.startswith("tt") and len(imdb) >= 9:
        return f"https://www.imdb.com/title/{imdb}/"
    return base


class MoobyBalmesScraper(BaseScraper):
    cinema_name = "Mooby Balmes"

    def fetch(self) -> List[Film]:
        import requests

        from utils import DEFAULT_HEADERS

        url = (os.getenv("MOOBY_BALMES_URL") or "").strip() or DEFAULT_URL
        r = requests.get(url, headers=DEFAULT_HEADERS, timeout=45)
        r.raise_for_status()
        html_text = r.text
        shops = _extract_shops_json(html_text)
        if not shops:
            logger.warning("Mooby Balmes: no s'ha trobat window.shops al HTML")
            return []

        shop = _find_balmes_shop(shops)
        if not shop:
            logger.warning("Mooby Balmes: cap botiga amb slug /balmes")
            return []

        films: List[Film] = []
        events = shop.get("events") or []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            title = (ev.get("locale_title") or ev.get("name") or "").strip()
            if not title:
                continue
            perfs = ev.get("performances") or []
            if not perfs:
                continue
            shows: List[Show] = []
            for p in perfs:
                if isinstance(p, dict):
                    sh = _perf_to_show(p)
                    if sh:
                        shows.append(sh)
            if not shows:
                continue
            films.append(
                Film(
                    cinema=self.cinema_name,
                    title=title,
                    url=_film_url_for_event(ev, url),
                    source_section="moobycinemas-embed",
                    shows=shows,
                    labels=[],
                )
            )

        logger.info("Mooby Balmes: %s pel·lícules amb sessions", len(films))
        return films
