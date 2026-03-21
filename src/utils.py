from __future__ import annotations

import re
import unicodedata

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CinemaAlertsBot/1.0; +https://github.com/)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,ca;q=0.8,en;q=0.7",
}


def normalize_title(title: str) -> str:
    title = title.strip().lower()
    title = unicodedata.normalize("NFKD", title)
    title = "".join(c for c in title if not unicodedata.combining(c))
    title = re.sub(
        r"\b(vose|vo|v\.o\.|doblada|subtitulada|subtitulado|"
        r"sesion especial|sesió especial|4k|3d|digital 2d)\b",
        "",
        title,
        flags=re.IGNORECASE,
    )
    title = re.sub(r"\s+", " ", title).strip()
    return title


def film_dedupe_key(cinema: str, title: str) -> str:
    return f"{cinema.strip().lower()}::{normalize_title(title)}"


def fetch_soup(url: str, *, timeout: float = 30, retries: int = 2):
    import time

    import requests
    from bs4 import BeautifulSoup

    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
            r.raise_for_status()
            return BeautifulSoup(r.content, "lxml")
        except Exception as e:
            last_exc = e
            if attempt < retries - 1:
                time.sleep(1.5)
    assert last_exc is not None
    raise last_exc
