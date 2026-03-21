from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Dict, Optional

import requests

from models import Film
from utils import DEFAULT_HEADERS, normalize_title

logger = logging.getLogger(__name__)


def sort_films_for_tmdb_priority(films: list[Film], tz_name: str) -> list[Film]:
    """
    Prioriza títulos con sesión en hoy/mañana para que no se queden sin nota
    por el límite TMDB_MAX_FILMS (antes: Verdi+Phenomena agotaban el cupo).
    """
    from zoneinfo import ZoneInfo

    from digest import parse_show_date, two_calendar_days

    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Europe/Madrid")
    d0, d1 = two_calendar_days(tz)
    win = {d0, d1}

    def in_window(f: Film) -> bool:
        for sh in f.shows:
            sd = parse_show_date(sh)
            if sd is not None and sd in win:
                return True
        return False

    return sorted(
        films,
        key=lambda f: (
            0 if in_window(f) else 1,
            f.cinema.lower(),
            f.title.lower(),
        ),
    )

# Nueva versión de caché si cambian criterios de confianza (evita notas viejas ★ 0.0)
_CACHE_FILENAME = "tmdb_cache_v2.json"


def _int_env(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or str(v).strip() == "":
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _clean_title_for_search(title: str) -> str:
    """Quita sufijos de sala/copia que rompen la búsqueda en TMDb."""
    t = re.sub(r"\s+", " ", title).strip()
    t = re.sub(
        r"\s*\([^)]*(?:proyección|proyecció|VOSE|VOSC|VOCAT|4K|Dolby|Atmos)[^)]*\)\s*",
        " ",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(r"\s+", " ", t).strip()
    return t[:120] if t else title[:120]

TMDB_SEARCH = "https://api.themoviedb.org/3/search/movie"
TMDB_MOVIE = "https://api.themoviedb.org/3/movie"


def _cache_path(data_dir: Path) -> Path:
    return data_dir / _CACHE_FILENAME


def _load_cache(path: Path) -> Dict[str, str]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(path: Path, cache: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def _search_movie(api_key: str, title: str) -> Optional[dict]:
    clean = _clean_title_for_search(title)
    clean = re.sub(r"\s*[\(\[].*?[\)\]]\s*", " ", clean).strip()
    if len(clean) < 2:
        return None
    r = requests.get(
        TMDB_SEARCH,
        params={
            "api_key": api_key,
            "query": clean[:120],
            "language": "es-ES",
            "include_adult": "false",
        },
        headers=DEFAULT_HEADERS,
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    results = data.get("results") or []
    if not results:
        return None
    return results[0]


def _movie_detail(api_key: str, movie_id: int) -> dict:
    r = requests.get(
        f"{TMDB_MOVIE}/{movie_id}",
        params={
            "api_key": api_key,
            "append_to_response": "external_ids",
            "language": "es-ES",
        },
        headers=DEFAULT_HEADERS,
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def _format_rating_line(
    vote: float,
    vote_count: int,
    imdb_id: Optional[str],
    tmdb_id: Optional[int] = None,
) -> str:
    parts = [f"★ {vote:.1f} TMDb"]
    if vote_count == 1:
        parts.append("(1 voto)")
    elif vote_count:
        parts.append(f"({vote_count} votos)")
    if imdb_id:
        parts.append(f'<a href="https://www.imdb.com/title/{imdb_id}/">IMDb</a>')
    elif tmdb_id:
        parts.append(
            f'<a href="https://www.themoviedb.org/movie/{tmdb_id}">TMDb</a>'
        )
    return " ".join(parts)


def _rating_is_reliable(vote: float, vote_count: int, min_votes: int) -> bool:
    """Evita ★ 0.0 y medias con casi ningún voto (match erróneo o película demasiado nueva)."""
    if vote <= 0.01:
        return False
    if vote_count < min_votes:
        return False
    return True


def enrich_films_with_ratings(
    films: list[Film],
    api_key: str | None,
    *,
    data_dir: Path,
    max_films: int = 50,
    delay_s: float = 0.12,
    min_votes: int | None = None,
) -> None:
    """
    Nota media desde TMDb + enlace IMDb si existe (mismo endpoint con external_ids).
    Requiere TMDB_API_KEY (gratis en themoviedb.org).
    """
    if not api_key:
        logger.info("TMDB_API_KEY no definida: sin notas.")
        return

    mv = min_votes if min_votes is not None else _int_env("TMDB_MIN_VOTES", 5)

    cache = _load_cache(_cache_path(data_dir))
    enriched = 0
    for film in films:
        if enriched >= max_films:
            logger.warning("TMDb: límite de películas (%s)", max_films)
            break
        key = normalize_title(film.title)
        if key in cache:
            v = cache[key]
            film.rating = v if v else None
            continue
        try:
            sm = _search_movie(api_key, film.title)
            time.sleep(delay_s)
            if not sm or not sm.get("id"):
                cache[key] = ""
                continue
            detail = _movie_detail(api_key, int(sm["id"]))
            time.sleep(delay_s)
            enriched += 1
            va = detail.get("vote_average")
            vc = detail.get("vote_count") or 0
            imdb_id = (detail.get("external_ids") or {}).get("imdb_id")
            tmdb_mid = int(sm["id"])
            if va is None:
                cache[key] = ""
                continue
            va_f = float(va)
            vc_i = int(vc)
            if not _rating_is_reliable(va_f, vc_i, mv):
                cache[key] = ""
                continue
            line = _format_rating_line(va_f, vc_i, imdb_id, tmdb_mid)
            cache[key] = line
            film.rating = line
        except Exception as e:
            logger.warning("TMDb: %s — %s", film.title[:60], e)
            cache[key] = ""

    _save_cache(_cache_path(data_dir), cache)
