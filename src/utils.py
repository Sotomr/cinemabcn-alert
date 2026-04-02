from __future__ import annotations

import re
import unicodedata

# Sufijos de sesión en cartelera (p. ej. Phenomena: título en MAYÚSCULAS + paréntesis).
_PROYECCION_TAIL = re.compile(
    r"\s*\([^)]*\bproyecci[oó]n\b[^)]*\)\s*$",
    re.IGNORECASE,
)


def _strip_trailing_proyeccion_parens(title: str) -> str:
    t = title.strip()
    while True:
        n = _PROYECCION_TAIL.sub("", t).strip()
        if n == t:
            break
        t = n
    return t


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


def film_title_dedupe_key(title: str) -> str:
    """
    Agrupa la misma película con distintas variantes de cartelera (VOSE con/sin
    paréntesis, Doblada ESP, etc.) para resúmenes y tops globales.
    Mayúsculas/minúsculas y acentos se normalizan; se quitan paréntesis tipo
    «(Proyección en 4K y VOSE)» (Phenomena y similares).
    """
    t = title.strip().lower()
    t = _strip_trailing_proyeccion_parens(t)
    for pat in (
        r"\s*\(VOSE\)\s*\(ATMOS\)\s*$",
        r"\s*\(VOSE\)\s*$",
        r"\s*\(VOSC\)\s*$",
        r"\s*\(VOCAT\)\s*$",
        r"\s*\(VO\)\s*$",
        r"\s*\(ATMOS\)\s*$",
        r"\s*\(IMAX\)\s*$",
        r"\s*\(4DX\)\s*$",
    ):
        t = re.sub(pat, "", t, flags=re.IGNORECASE)
    t = re.sub(
        r"\s+(VOSE|VOSC|VOCAT|VOI|V\.O\.|V\.O\.S\.E\.|V\.O\.S\.C\.)\s*$",
        "",
        t,
        flags=re.IGNORECASE,
    ).strip()
    t = re.sub(
        r"\s+Doblada\s+(ESP|CAT|Cast|Català|Catalan)\s*$",
        "",
        t,
        flags=re.IGNORECASE,
    ).strip()
    t = re.sub(r"\s+\bVO\b\s*$", "", t, flags=re.IGNORECASE).strip()
    t = normalize_title(t)
    t = re.sub(r"\(\s*\)", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def global_top_display_title(title: str) -> str:
    """Título más corto para el resumen global (quita sufijos de sesión)."""
    t = title.strip()
    t = _strip_trailing_proyeccion_parens(t)
    for pat in (
        r"\s*\(VOSE\)\s*\(ATMOS\)\s*$",
        r"\s*\(VOSE\)\s*$",
        r"\s*\(VOSC\)\s*$",
        r"\s*\(VOCAT\)\s*$",
        r"\s*\(ATMOS\)\s*$",
    ):
        t = re.sub(pat, "", t, flags=re.IGNORECASE)
    t = re.sub(
        r"\s+(VOSE|VOSC|VOCAT|VOI)\s*$",
        "",
        t,
        flags=re.IGNORECASE,
    ).strip()
    t = re.sub(
        r"\s+Doblada\s+(ESP|CAT|Cast|Català|Catalan)\s*$",
        "",
        t,
        flags=re.IGNORECASE,
    ).strip()
    # Estètica al digest (Telegram): Phenomena i altres solen posar títols en MAJÚSCULES.
    return t.lower().strip()


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
