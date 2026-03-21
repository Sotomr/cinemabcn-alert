from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Dict, Optional

import requests

from models import Film
from utils import DEFAULT_HEADERS, normalize_title

logger = logging.getLogger(__name__)

TMDB_SEARCH = "https://api.themoviedb.org/3/search/movie"
TMDB_MOVIE = "https://api.themoviedb.org/3/movie"


def _cache_path(data_dir: Path) -> Path:
    return data_dir / "tmdb_cache.json"


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
    clean = re.sub(r"\s+", " ", title).strip()
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


def _format_rating_line(vote: float, vote_count: int, imdb_id: Optional[str]) -> str:
    parts = [f"★ {vote:.1f} TMDb"]
    if vote_count:
        parts.append(f"({vote_count} votos)")
    if imdb_id:
        parts.append(f'<a href="https://www.imdb.com/title/{imdb_id}/">IMDb</a>')
    return " ".join(parts)


def enrich_films_with_ratings(
    films: list[Film],
    api_key: str | None,
    *,
    data_dir: Path,
    max_films: int = 50,
    delay_s: float = 0.12,
) -> None:
    """
    Nota media desde TMDb + enlace IMDb si existe (mismo endpoint con external_ids).
    Requiere TMDB_API_KEY (gratis en themoviedb.org).
    """
    if not api_key:
        logger.info("TMDB_API_KEY no definida: sin notas.")
        return

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
            if va is None:
                cache[key] = ""
                continue
            line = _format_rating_line(float(va), int(vc), imdb_id)
            cache[key] = line
            film.rating = line
        except Exception as e:
            logger.warning("TMDb: %s — %s", film.title[:60], e)
            cache[key] = ""

    _save_cache(_cache_path(data_dir), cache)
