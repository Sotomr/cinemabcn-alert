from __future__ import annotations

from typing import Iterable, List, Set

from models import Film
from utils import film_dedupe_key, normalize_title


def previous_key_set(previous_films: Iterable[Film]) -> Set[str]:
    return {film_dedupe_key(f.cinema, f.title) for f in previous_films}


def compute_new_entries(previous_films: List[Film], current_films: List[Film]) -> List[Film]:
    prev = previous_key_set(previous_films)
    out: List[Film] = []
    seen: Set[str] = set()
    for film in current_films:
        key = film_dedupe_key(film.cinema, film.title)
        if key in seen:
            continue
        seen.add(key)
        if key not in prev:
            out.append(film)
    return out


def titles_for_compare(films: Iterable[Film]) -> Set[str]:
    return {normalize_title(f.title) for f in films}
