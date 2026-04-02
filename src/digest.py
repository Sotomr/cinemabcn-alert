from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from models import Film, Show
from utils import film_title_dedupe_key, global_top_display_title

_WEEKDAY_CA = (
    "dilluns",
    "dimarts",
    "dimecres",
    "dijous",
    "divendres",
    "dissabte",
    "diumenge",
)
_MONTH_CA = (
    "gen",
    "febr",
    "març",
    "abr",
    "maig",
    "juny",
    "jul",
    "ag",
    "set",
    "oct",
    "nov",
    "des",
)

# Separador visual (Telegram HTML)
_SEP = "────────────"


@dataclass(frozen=True)
class DigestLimits:
    """Límites para que el mensaje sea legible en Telegram."""

    max_films_unscheduled_per_cinema: int = 15
    max_films_verdi_per_day: int = 0  # 0 = sin límite
    show_debug_footer: bool = False
    global_top_per_day: int = 12  # 0 = no mostrar bloque global
    top_films_per_cinema_per_day: int = 3
    extra_unrated_per_cinema_per_day: int = 0
    novelties_top_per_cinema: int = 5
    novelties_max_lines: int = 15
    only_today: bool = False


def _fmt_day_header(d: date, label: str) -> str:
    wd = _WEEKDAY_CA[d.weekday()].capitalize()
    mon = _MONTH_CA[d.month - 1]
    return f"{label} · {wd} {d.day} {mon}"


def parse_show_date(show: Show) -> date | None:
    m = re.match(r"^(\d{8})\s+(\d{2}:\d{2})\s*$", (show.datetime or "").strip())
    if not m:
        return None
    ds = m.group(1)
    try:
        return date(int(ds[:4]), int(ds[4:6]), int(ds[6:8]))
    except ValueError:
        return None


def parse_show_time(show: Show) -> str | None:
    m = re.match(r"^(\d{8})\s+(\d{2}:\d{2})\s*$", (show.datetime or "").strip())
    return m.group(2) if m else None


def two_calendar_days(tz: ZoneInfo) -> Tuple[date, date]:
    """Solo hoy y mañana (ventana útil para decidir sesión)."""
    today = datetime.now(tz).date()
    return today, today + timedelta(days=1)


def film_has_show_in_window(film: Film, tz_name: str) -> bool:
    """True si la película tiene al menos una sesión hoy o mañana."""
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Europe/Madrid")
    d0, d1 = two_calendar_days(tz)
    win = {d0, d1}
    for sh in film.shows:
        sd = parse_show_date(sh)
        if sd is not None and sd in win:
            return True
    return False


def score_from_rating_html(rating_html: Optional[str]) -> float:
    """Extrae la nota numérica del HTML de TMDb para ordenar."""
    if not rating_html:
        return -1.0
    m = re.search(r"★\s*([\d.]+)", rating_html)
    if not m:
        return -1.0
    try:
        return float(m.group(1))
    except ValueError:
        return -1.0


def _global_top_lines(
    day_block: Dict[str, List[Tuple[str, List[str], Optional[str]]]],
    max_titles: int,
) -> List[str]:
    """
    Top por nota entre títulos con ★; agrupa por título normalizado y lista cines
    donde hay sesión ese día.
    """
    if max_titles <= 0:
        return []
    best: Dict[str, Dict[str, Any]] = {}
    for cinema, rows in day_block.items():
        for title, _times, rating in rows:
            sc = score_from_rating_html(rating)
            if sc < 0:
                continue
            nk = film_title_dedupe_key(title)
            if nk not in best:
                best[nk] = {
                    "score": sc,
                    "title": title,
                    "rating": rating,
                    "cinemas": {cinema},
                }
            else:
                b = best[nk]
                b["cinemas"].add(cinema)
                if sc > b["score"]:
                    b["score"] = sc
                    b["title"] = title
                    b["rating"] = rating
    items = sorted(best.values(), key=lambda x: (-x["score"], x["title"].lower()))
    items = items[:max_titles]
    if not items:
        return []
    lines: List[str] = [
        "<b>Millors per nota</b>",
        "",
    ]
    for i, it in enumerate(items, start=1):
        cin_html = ", ".join(
            f"<b>{html.escape(c)}</b>"
            for c in sorted(it["cinemas"], key=str.lower)
        )
        disp = global_top_display_title(it["title"])
        t_esc = html.escape(disp)
        note = f" {it['rating']}" if it.get("rating") else ""
        lines.append(f"   {i}. {t_esc} · {cin_html}{note}")
    lines.append("")
    return lines


def _collect_by_day_cinema(
    films: List[Film],
    day_list: List[Tuple[date, str]],
) -> Dict[date, Dict[str, List[Tuple[str, List[str], Optional[str]]]]]:
    target_dates = {d for d, _ in day_list}
    by_day_cinema: Dict[
        date, Dict[str, List[Tuple[str, List[str], Optional[str]]]]
    ] = {d: {} for d, _ in day_list}

    for film in films:
        if not film.shows:
            continue

        by_date: Dict[date, List[str]] = {}
        for sh in film.shows:
            sd = parse_show_date(sh)
            if sd is None or sd not in target_dates:
                continue
            tm = parse_show_time(sh) or ""
            if tm:
                by_date.setdefault(sd, []).append(tm)

        if not by_date:
            continue

        for sd, times in by_date.items():
            times_u = sorted(set(times))
            title = film.title
            cin = film.cinema
            lst = by_day_cinema.setdefault(sd, {}).setdefault(cin, [])
            found = False
            for i, (t, hs, r0) in enumerate(lst):
                if t == title:
                    merged = sorted(set(hs + times_u))
                    lst[i] = (t, merged, r0 or film.rating)
                    found = True
                    break
            if not found:
                lst.append((title, times_u, film.rating))

    return by_day_cinema


def _format_cinema_rows(
    cinema: str,
    raw: List[Tuple[str, List[str], Optional[str]]],
    lim: DigestLimits,
) -> List[str]:
    """Líneas de listado (viñetas) para un cine en un día."""
    lines: List[str] = []
    orig_count = len(raw)
    rated = [x for x in raw if score_from_rating_html(x[2]) >= 0.0]
    unrated = [x for x in raw if score_from_rating_html(x[2]) < 0.0]
    rated.sort(key=lambda x: (-score_from_rating_html(x[2]), x[0].lower()))
    unrated.sort(key=lambda x: x[0].lower())

    max_v = lim.max_films_verdi_per_day
    top_n = lim.top_films_per_cinema_per_day
    extra_u = lim.extra_unrated_per_cinema_per_day

    if top_n > 0:
        show_r = rated[:top_n]
        hide_r = max(0, len(rated) - len(show_r))
        if show_r:
            show_u = unrated[:extra_u] if extra_u > 0 else []
            hide_u = max(0, len(unrated) - len(show_u))
        else:
            cap = top_n + (extra_u if extra_u > 0 else 0)
            show_u = unrated[:cap]
            hide_u = max(0, len(unrated) - len(show_u))
            show_r = []
            hide_r = 0
    else:
        rows_all = sorted(
            raw,
            key=lambda x: (-score_from_rating_html(x[2]), x[0].lower()),
        )
        if cinema == "Verdi" and max_v > 0:
            rows_all = rows_all[:max_v]
        show_r = rows_all
        show_u = []
        hide_r = hide_u = 0

    def _emit(title: str, times: List[str], rating: Optional[str]) -> None:
        t_esc = html.escape(title)
        note = f" {rating}" if rating else ""
        if times:
            horas = ", ".join(html.escape(x) for x in times)
            lines.append(f"    • {t_esc} — {horas}{note}")
        else:
            lines.append(f"    • {t_esc}{note}")

    for title, times, rating in show_r:
        _emit(title, times, rating)
    if show_u:
        lines.append(
            "<i>    Sense ★ TMDb (sense coincidència o pocs vots a TMDb):</i>"
        )
        for title, times, rating in show_u:
            _emit(title, times, rating)
    hidden = hide_r + hide_u
    if hidden:
        lines.append(f"<i>    … i {hidden} més</i>")
    return lines


def _build_global_top(
    by_day_cinema: Dict[date, Dict[str, List[Tuple[str, List[str], Optional[str]]]]],
    day_list: List[Tuple[date, str]],
    max_titles: int,
) -> List[Dict[str, Any]]:
    """
    Build a unified top-N across all days, deduped by title.
    Returns list of dicts with score, title, rating, cinemas (set of names),
    and schedule: {date: {cinema: [times]}}.
    """
    best: Dict[str, Dict[str, Any]] = {}
    for d, _lab in day_list:
        block = by_day_cinema.get(d, {})
        for cinema, rows in block.items():
            for title, times, rating in rows:
                sc = score_from_rating_html(rating)
                if sc < 0:
                    continue
                nk = film_title_dedupe_key(title)
                if nk not in best:
                    best[nk] = {
                        "score": sc,
                        "title": title,
                        "rating": rating,
                        "cinemas": {cinema},
                        "schedule": {},
                    }
                else:
                    b = best[nk]
                    b["cinemas"].add(cinema)
                    if sc > b["score"]:
                        b["score"] = sc
                        b["title"] = title
                        b["rating"] = rating
                    elif sc == b["score"]:
                        d_new = len(global_top_display_title(title))
                        d_old = len(global_top_display_title(b["title"]))
                        u_old = b["title"].strip().isupper()
                        u_new = title.strip().isupper()
                        if d_new < d_old or (u_old and not u_new):
                            b["title"] = title
                            if rating:
                                b["rating"] = rating
                sched = best[nk]["schedule"]
                sched.setdefault(d, {}).setdefault(cinema, []).extend(times)
    for entry in best.values():
        for d in entry["schedule"]:
            for cin in entry["schedule"][d]:
                entry["schedule"][d][cin] = sorted(set(entry["schedule"][d][cin]))
    items = sorted(best.values(), key=lambda x: (-x["score"], x["title"].lower()))
    return items[:max_titles] if max_titles > 0 else items


def build_digest_telegram_parts(
    films: List[Film],
    failures: List[str],
    *,
    tz_name: str = "Europe/Madrid",
    limits: DigestLimits | None = None,
) -> List[str]:
    """
    Mensaje 1: top 10 global (hoy+mañana) con nota y cines.
    Mensaje 2: los mismos 10 con horarios detallados por cine y día.
    """
    lim = limits or DigestLimits()
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Europe/Madrid")

    d0, d1 = two_calendar_days(tz)
    day_list: List[Tuple[date, str]] = [(d0, "Avui"), (d1, "Demà")]
    by_day_cinema = _collect_by_day_cinema(films, day_list)

    top = _build_global_top(by_day_cinema, day_list, lim.global_top_per_day)

    now_str = datetime.now(tz).strftime("%d/%m/%Y %H:%M")
    hoy_hdr = _fmt_day_header(d0, "Avui")

    # --- Message 1: ranked list ---
    msg1: List[str] = [
        f"<b>Cartellera BCN · {html.escape(hoy_hdr)}</b>",
        f"<i>actualitzat {html.escape(now_str)}</i>",
        "",
        _SEP,
        f"<b>Les {lim.global_top_per_day} millors per nota (avui + demà)</b>",
        "",
    ]
    if top:
        for i, it in enumerate(top, start=1):
            cin_html = ", ".join(
                f"<b>{html.escape(c)}</b>"
                for c in sorted(it["cinemas"], key=str.lower)
            )
            disp = global_top_display_title(it["title"])
            t_esc = html.escape(disp)
            note = f" {it['rating']}" if it.get("rating") else ""
            msg1.append(f"   {i}. {t_esc} · {cin_html}{note}")
    else:
        msg1.append("<i>Sense notes TMDb en aquesta passada.</i>")

    notes_extra = _cinema_notes_sin_ventana(films, by_day_cinema, day_list)
    if notes_extra:
        msg1.extend(["", _SEP, ""] + notes_extra)

    if failures:
        fl = ["", _SEP, "", "<b>Avísos</b>", ""]
        for f in failures:
            fl.append(f"   • {html.escape(f)}")
        msg1.extend(fl)

    out: List[str] = ["\n".join(msg1).strip()]

    # --- Message 2: detailed schedules for those top films ---
    if top:
        msg2: List[str] = [
            f"<b>Horaris — Top {lim.global_top_per_day}</b>",
            "",
        ]
        for i, it in enumerate(top, start=1):
            disp = global_top_display_title(it["title"])
            t_esc = html.escape(disp)
            note = f" {it['rating']}" if it.get("rating") else ""
            msg2.append(f"<b>{i}. {t_esc}</b>{note}")
            sched = it["schedule"]
            for d, lab in day_list:
                if d not in sched:
                    continue
                cinemas_today = sched[d]
                for cin in sorted(cinemas_today.keys(), key=str.lower):
                    times = cinemas_today[cin]
                    horas = ", ".join(times)
                    msg2.append(f"    {html.escape(cin)} · {lab.lower()} — {horas}")
            msg2.append("")
        out.append("\n".join(msg2).strip())

    return [s for s in out if s.strip()]


def _cinema_notes_sin_ventana(
    films: List[Film],
    by_day_cinema: Dict[date, Dict[str, Any]],
    day_list: List[Tuple[date, str]],
) -> List[str]:
    """Avisos cuando un cine aporta títulos pero ninguno entra en hoy/mañana."""
    present: set[str] = set()
    for d, _ in day_list:
        present |= set(by_day_cinema.get(d, {}).keys())
    by_cinema: Dict[str, List[Film]] = {}
    for f in films:
        by_cinema.setdefault(f.cinema, []).append(f)
    notes: List[str] = []
    multi_day = len(day_list) > 1
    for cin, flist in sorted(by_cinema.items(), key=lambda x: x[0].lower()):
        if cin in present or not flist:
            continue
        if cin == "Phenomena":
            if multi_day:
                notes.append(
                    f"<i><b>{html.escape(cin)}</b>: les sessions de la web no "
                    f"coincideixen amb avui ni demà (sovint són dates posteriors).</i>"
                )
            else:
                notes.append(
                    f"<i><b>{html.escape(cin)}</b>: les sessions de la web no "
                    f"coincideixen amb avui (sovint són dates posteriors).</i>"
                )
        else:
            if multi_day:
                notes.append(
                    f"<i><b>{html.escape(cin)}</b>: sense sessions avui ni demà "
                    f"segons les dades obtingudes.</i>"
                )
            else:
                notes.append(
                    f"<i><b>{html.escape(cin)}</b>: sense sessions avui.</i>"
                )
    return notes


def build_digest_sections(
    films: List[Film],
    failures: List[str],
    *,
    tz_name: str = "Europe/Madrid",
    limits: DigestLimits | None = None,
) -> List[str]:
    """
    Devuelve trozos HTML listos para enviar: cada trozo es una sección coherente
    (un día, un cine en cartelera, errores…) para no cortar a mitad de lista.
    """
    lim = limits or DigestLimits()
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Europe/Madrid")

    d0, d1 = two_calendar_days(tz)
    if lim.only_today:
        day_list = [(d0, "Avui")]
    else:
        day_list = [(d0, "Avui"), (d1, "Demà")]
    by_day_cinema = _collect_by_day_cinema(films, day_list)

    sections: List[str] = []

    now_str = datetime.now(tz).strftime("%d/%m/%Y %H:%M")
    day_header = _fmt_day_header(d0, "Avui")
    header_lines: List[str] = [
        f"<b>Cartellera · {html.escape(day_header)}</b>",
        f"<i>Barcelona · actualitzat {html.escape(now_str)}</i>",
    ]
    header_lines.extend(["", _SEP])
    sections.append("\n".join(header_lines))

    # Un bloque por día
    for idx, (d, lab) in enumerate(day_list):
        lines: List[str] = [
            f"<b>{html.escape(_fmt_day_header(d, lab))}</b>",
            "",
        ]
        block = by_day_cinema.get(d, {})
        if not block:
            lines.append(
                "<i>Cap sessió amb hora en aquest període (segons les webs consultades).</i>"
            )
        else:
            g_lines = _global_top_lines(block, lim.global_top_per_day)
            if g_lines:
                lines.extend(g_lines)
            if g_lines:
                lines.append("<b>2) Per cinema</b> — horaris i sessions")
                lines.append("")
            else:
                lines.append("<b>Per cinema</b> — horaris i sessions")
                lines.append("")
            for cix, cinema in enumerate(sorted(block.keys())):
                if cix:
                    lines.append("")
                lines.append(f"<b>{html.escape(cinema)}</b>")
                lines.extend(
                    _format_cinema_rows(cinema, block[cinema], lim),
                )
        chunk = "\n".join(lines).strip()
        if idx < len(day_list) - 1:
            chunk += f"\n\n{_SEP}"
        sections.append(chunk)

    notes_extra = _cinema_notes_sin_ventana(films, by_day_cinema, day_list)
    if notes_extra:
        sections.append("\n".join([_SEP, ""] + notes_extra))

    if failures:
        fl = [
            _SEP,
            "<b>Avísos</b>",
            "<i>Alguna web no s'ha pogut llegir bé en aquesta passada.</i>",
            "",
        ]
        for f in failures:
            fl.append(f"   • {html.escape(f)}")
        sections.append("\n".join(fl))

    if lim.show_debug_footer:
        sections.append(
            "<i>Depuració: GitHub Actions → Run workflow · "
            "local: <code>python src/main.py</code></i>"
        )

    return [s for s in sections if s.strip()]


def expand_digest_parts_for_telegram(
    parts: List[str], max_len: int = 3800
) -> List[str]:
    """Parte cada trozo del digest si supera max_len (p. ej. un solo cine muy largo)."""
    out: List[str] = []
    for p in parts:
        out.extend(merge_sections_for_telegram([p], max_len=max_len))
    return out


def merge_sections_for_telegram(sections: List[str], max_len: int = 3800) -> List[str]:
    """
    Une secciones en varios mensajes sin superar max_len.
    Si una sola sección es demasiado larga, la parte por líneas.
    """
    messages: List[str] = []
    buf = ""

    def flush() -> None:
        nonlocal buf
        if buf.strip():
            messages.append(buf.strip())
        buf = ""

    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        add = sec if not buf else buf + "\n\n" + sec
        if len(add) <= max_len:
            buf = add
            continue
        flush()
        if len(sec) <= max_len:
            buf = sec
        else:
            for part in _split_oversized_section(sec, max_len):
                messages.append(part)
    flush()
    return messages


def _split_oversized_section(text: str, max_len: int) -> List[str]:
    lines = text.split("\n")
    parts: List[str] = []
    cur: List[str] = []
    cur_len = 0
    for line in lines:
        line_len = len(line) + 1
        if cur and cur_len + line_len > max_len:
            parts.append("\n".join(cur))
            cur = [line]
            cur_len = line_len
        else:
            cur.append(line)
            cur_len += line_len
    if cur:
        parts.append("\n".join(cur))
    return parts


def format_daily_digest_html(
    films: List[Film],
    failures: List[str],
    *,
    tz_name: str = "Europe/Madrid",
    limits: DigestLimits | None = None,
) -> str:
    """Un solo string (p. ej. logs); usa build_digest_sections (vista continua)."""
    parts = build_digest_sections(films, failures, tz_name=tz_name, limits=limits)
    return "\n\n".join(parts).strip()


def format_novelties_html(
    films: List[Film],
    *,
    top_per_cinema: int = 5,
    max_lines: int = 15,
) -> str:
    """Solo hoy/mañana: filtrar antes de llamar. Top por cine por nota."""
    if not films:
        return ""
    by_cin: Dict[str, List[Film]] = {}
    for f in films:
        by_cin.setdefault(f.cinema, []).append(f)
    picked: List[Film] = []
    for cin in sorted(by_cin.keys(), key=str.lower):
        grp = sorted(
            by_cin[cin],
            key=lambda f: (-score_from_rating_html(f.rating), f.title.lower()),
        )
        picked.extend(grp[: max(0, top_per_cinema)])
    picked.sort(
        key=lambda f: (
            f.cinema.lower(),
            -score_from_rating_html(f.rating),
            f.title.lower(),
        )
    )
    lines = [
        _SEP,
        "<b>Novetats</b>",
        "<i>Noves amb sessió avui o demà; ordenades per nota TMDb.</i>",
        "",
    ]
    shown = picked[:max_lines]
    for f in shown:
        note = f" {f.rating}" if f.rating else ""
        lines.append(
            f"   • <b>{html.escape(f.cinema)}</b> · {html.escape(f.title)}{note}"
        )
    if len(picked) > max_lines:
        lines.append(f"   <i>… i {len(picked) - max_lines} més</i>")
    return "\n".join(lines)
