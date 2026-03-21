from __future__ import annotations

import json
import logging
import os
import re
import time
import unicodedata
from difflib import SequenceMatcher
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
_CACHE_FILENAME = "tmdb_cache_v7.json"


def _int_env(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or str(v).strip() == "":
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _clean_title_for_search(title: str) -> str:
    """Quita sufijos VO/versión y ruido para buscar en TMDb (es/ca/en)."""
    t = re.sub(r"\s+", " ", title).strip()
    for pat in (
        r"\(VOSE\)",
        r"\(VOSC\)",
        r"\(VOCAT\)",
        r"\(VO\)",
        r"\(ATMOS\)",
        r"\(4K\)",
        r"\(3D\)",
        r"\(HFR\)",
        r"\(Doblada ESP\)",
        r"\(Doblada Cat\)",
        r"\(En directo\)",
        r"\(Proyección[^)]*\)",
        r"\(proyección[^)]*\)",
    ):
        t = re.sub(pat, "", t, flags=re.IGNORECASE)
    t = re.sub(
        r"\s*\([^)]*(?:proyección|proyecció|VOSE|VOSC|VOCAT|4K|Dolby|Atmos)[^)]*\)\s*",
        " ",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(r"\s*\([^)]*\)", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if " - " in t and len(t) > 42:
        t = t.split(" - ")[0].strip()
    # Verdi y otros: "Pillion VOSE", "El agente secreto VOSE" (sin paréntesis)
    t = re.sub(
        r"\s+(VOSE|VOSC|VOCAT|VOI|V\.O\.|V\.O\.S\.E\.|V\.O\.S\.C\.)\s*$",
        "",
        t,
        flags=re.IGNORECASE,
    ).strip()
    t = re.sub(r"\s+\bVO\b\s*$", "", t, flags=re.IGNORECASE).strip()
    # "Little Amélie Doblada ESP" (sin paréntesis)
    t = re.sub(
        r"\s+Doblada\s+(ESP|CAT|Cast|Català|Catalan)\s*$",
        "",
        t,
        flags=re.IGNORECASE,
    ).strip()
    return t[:120] if t else title[:120]


def _normalize_for_match(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9\s]", " ", s.lower())
    s = re.sub(r"\s+", " ", s).strip()
    return s


def score_tmdb_title_match(query_clean: str, result: dict) -> float:
    """
    Similitud 0–1 entre la consulta limpia y title/original_title del resultado TMDb.
    Mejor que elegir solo por popularidad (fallaba con títulos locales o traducciones).
    """
    qn = _normalize_for_match(query_clean)
    if not qn:
        return 0.0
    best = 0.0
    for key in ("title", "original_title"):
        raw = result.get(key)
        if not raw or not str(raw).strip():
            continue
        tn = _normalize_for_match(str(raw))
        if not tn:
            continue
        seq = SequenceMatcher(None, qn, tn).ratio()
        qset = set(qn.split())
        tset = set(tn.split())
        jac = 0.0
        if qset and tset:
            jac = len(qset & tset) / len(qset | tset)
        blended = max(seq, jac)
        if qn == tn:
            blended = 1.0
        elif qn in tn or tn in qn:
            blended = max(blended, 0.82)
        best = max(best, blended)
    return best


def pick_best_tmdb_search_result(
    query_clean: str, results: list[dict]
) -> Optional[dict]:
    """
    Elige el mejor candidato de la lista de resultados de /search/movie.
    Si la similitud es muy baja en todos, mantiene el comportamiento antiguo (más popular).
    """
    if not results:
        return None
    scored: list[tuple[float, float, dict]] = []
    for r in results:
        if not r.get("id"):
            continue
        s = score_tmdb_title_match(query_clean, r)
        pop = float(r.get("popularity") or 0.0)
        scored.append((s, pop, r))
    if not scored:
        return None
    scored.sort(key=lambda x: (-x[0], -x[1]))
    best_s, _, best_r = scored[0]
    if best_s >= 0.38:
        return best_r
    return max((x[2] for x in scored), key=lambda x: float(x.get("popularity") or 0.0))


def _search_query_variants(clean: str) -> list[str]:
    """Variantes para cuando el título en cartelera no coincide con el de TMDb."""
    out: list[str] = []
    if clean and len(clean) >= 2:
        out.append(clean.strip())
    for sep in (" — ", " – ", " - "):
        if sep in clean:
            head = clean.split(sep)[0].strip()
            if len(head) >= 3:
                out.append(head)
    stripped = re.sub(
        r"^(el|la|los|las|les|els|un|una|uns|unes|l\'|ll\')\s+",
        "",
        clean.strip(),
        flags=re.IGNORECASE,
    ).strip()
    if stripped != clean.strip() and len(stripped) >= 3:
        out.append(stripped)
    # Catalan: "L'arquitecte" vs ficha "El arquitecto" / "The Architect"
    if re.match(r"^l['\u2019]", clean.strip(), re.I):
        tail = re.sub(r"^l['\u2019]\s*", "", clean.strip(), count=1, flags=re.I).strip()
        if len(tail) >= 3:
            out.append(tail)
    seen: set[str] = set()
    uniq: list[str] = []
    for x in out:
        k = x.casefold()
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    return uniq[:5]


def _merge_tmdb_results(pool: dict[int, dict], results: list[dict]) -> None:
    for r in results:
        mid = r.get("id")
        if mid is None:
            continue
        mid = int(mid)
        pop = float(r.get("popularity") or 0.0)
        prev = pool.get(mid)
        if prev is None or pop > float(prev.get("popularity") or 0.0):
            pool[mid] = r


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


def _search_movie(
    api_key: str, title: str, *, delay_s: float = 0.12
) -> Optional[dict]:
    clean = _clean_title_for_search(title)
    clean = re.sub(r"\s*[\(\[].*?[\)\]]\s*", " ", clean).strip()
    if len(clean) < 2:
        return None
    q_base = clean[:120]
    variants = _search_query_variants(q_base)

    pool: dict[int, dict] = {}
    steps: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add_step(q: str, lang: str) -> None:
        if len(q) < 2:
            return
        k = (q.casefold(), lang)
        if k not in seen:
            seen.add(k)
            steps.append((q, lang))

    v0 = variants[0]
    add_step(v0, "es-ES")
    add_step(v0, "en-US")
    if len(variants) > 1:
        add_step(variants[1], "es-ES")
        add_step(variants[1], "en-US")
    add_step(v0, "ca-ES")

    step_slice = steps[:6]
    for i, (q, lang) in enumerate(step_slice):
        r = requests.get(
            TMDB_SEARCH,
            params={
                "api_key": api_key,
                "query": q[:120],
                "language": lang,
                "region": "ES",
                "include_adult": "false",
            },
            headers=DEFAULT_HEADERS,
            timeout=20,
        )
        r.raise_for_status()
        _merge_tmdb_results(pool, (r.json().get("results") or [])[:20])
        if i < len(step_slice) - 1:
            time.sleep(delay_s)
        if not pool:
            continue
        merged = list(pool.values())
        best = pick_best_tmdb_search_result(q_base, merged)
        if best and score_tmdb_title_match(q_base, best) >= 0.68:
            return best

    if not pool:
        return None
    return pick_best_tmdb_search_result(q_base, list(pool.values()))


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
    """
    Evita ★ 0.0. TMDB_MIN_VOTES filtra estrenos con pocos votos en TMDb (no en IMDb):
    una película famosa puede tener ya nota en IMDb pero aún <N votos en TMDb.
    """
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

    mv = min_votes if min_votes is not None else _int_env("TMDB_MIN_VOTES", 1)

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
            sm = _search_movie(api_key, film.title, delay_s=delay_s)
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
