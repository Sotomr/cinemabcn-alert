from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import FrozenSet, List

from models import Film

PRIMARY_RELEASE_WEEK = "release_week"
PRIMARY_NEW_ON_BOARD = "new_on_board"
PRIMARY_SPECIAL_EVENT = "special_event"

TAG_CLASSIC = "classic"
TAG_RETROSPECTIVE = "retrospective"
TAG_ANIME = "anime"
TAG_OPERA_BALLET = "opera_ballet"
TAG_FAMILY = "family"

_SPECIAL = re.compile(
    r"\b("
    r"clásico|clàssic|clasic|classic|aniversari|aniversario|retrospectiv|ciclo|cicle|"
    r"remaster|imprescindible|òpera|ópera|opera|ballet|reestreno|reestrena|"
    r"marat[oó]|sessi[oó]\s+teta|matins\s+d|dimecres\s+cultural|"
    r"anime\s+day|bcn\s*26"
    r")\b",
    re.IGNORECASE,
)

_ESTRENO = re.compile(
    r"\b(estreno|estrena|estren)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Classification:
    primary: str
    secondary_tags: tuple[str, ...]


def _blob(film: Film) -> str:
    return " ".join([film.title, film.source_section, " ".join(film.labels)]).lower()


def _secondary_tags(film: Film) -> tuple[str, ...]:
    tags: List[str] = []
    b = _blob(film)
    if _SPECIAL.search(b):
        if re.search(r"òpera|ópera|opera|ballet", b, re.I):
            tags.append(TAG_OPERA_BALLET)
        if re.search(r"anime", b, re.I):
            tags.append(TAG_ANIME)
        if re.search(r"retrospectiv", b, re.I):
            tags.append(TAG_RETROSPECTIVE)
        if re.search(r"clasic|clàssic|classic", b, re.I):
            tags.append(TAG_CLASSIC)
        if re.search(r"kids|familiar", b, re.I):
            tags.append(TAG_FAMILY)
    return tuple(dict.fromkeys(tags))


def _special_section(film: Film) -> bool:
    s = film.source_section.lower()
    return any(
        k in s
        for k in (
            "cicle",
            "ciclo",
            "matins",
            "òpera",
            "ópera",
            "ballet",
            "anime day",
            "dimecres",
            "dijous",
            "imprescindible",
            "sessió teta",
            "sessio teta",
            "verdi club",
            "promoció",
            "promocion",
        )
    )


def classify_film(
    film: Film,
    *,
    previous_titles_norm: FrozenSet[str],
    week_start: date,
    week_end: date,
) -> Classification:
    sec = _secondary_tags(film)
    b = _blob(film)

    if _special_section(film) or _SPECIAL.search(b):
        return Classification(primary=PRIMARY_SPECIAL_EVENT, secondary_tags=sec)

    if _ESTRENO.search(b) or any(
        _ESTRENO.search(lb) for lb in film.labels
    ):
        return Classification(primary=PRIMARY_RELEASE_WEEK, secondary_tags=sec)

    nt = _norm_title(film.title)
    if nt not in previous_titles_norm and _date_in_week_in_text(film, week_start, week_end):
        return Classification(primary=PRIMARY_RELEASE_WEEK, secondary_tags=sec)

    return Classification(primary=PRIMARY_NEW_ON_BOARD, secondary_tags=sec)


def _norm_title(s: str) -> str:
    s = s.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def _date_in_week_in_text(film: Film, week_start: date, week_end: date) -> bool:
    blob = " ".join([film.title, film.source_section] + film.labels)
    for m in re.finditer(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](20\d{2})\b", blob):
        try:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if week_start <= d <= week_end:
                return True
        except ValueError:
            continue
    return False


def week_bounds_today() -> tuple[date, date]:
    today = datetime.now().date()
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    return start, end
