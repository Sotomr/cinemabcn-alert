from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from models import Film, Show
from utils import normalize_title

_WEEKDAY_ES = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)
_MONTH_ES = (
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
)

# Separador visual (Telegram HTML)
_SEP = "────────────"


@dataclass(frozen=True)
class DigestLimits:
    """Límites para que el mensaje sea legible en Telegram."""

    max_films_unscheduled_per_cinema: int = 15
    max_films_verdi_per_day: int = 0  # 0 = sin límite
    show_debug_footer: bool = False
    # Resumen al inicio de cada día: hasta N títulos con ★ (agrupados por título normalizado).
    global_top_per_day: int = 10  # 0 = no mostrar bloque global
    # 0 = listar todas las sesiones por cine/día ordenadas por nota; >0 = tope antiguo + pie.
    top_films_per_cinema_per_day: int = 0
    extra_unrated_per_cinema_per_day: int = 5
    novelties_top_per_cinema: int = 5
    novelties_max_lines: int = 15


def _fmt_day_header(d: date, label: str) -> str:
    wd = _WEEKDAY_ES[d.weekday()].capitalize()
    mon = _MONTH_ES[d.month - 1]
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
            nk = normalize_title(title)
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
        f"<b>Top por nota TMDb</b> (hasta {max_titles} títulos con ★)",
        "",
    ]
    for i, it in enumerate(items, start=1):
        cin_s = ", ".join(sorted(it["cinemas"], key=str.lower))
        t_esc = html.escape(it["title"])
        note = f" {it['rating']}" if it.get("rating") else ""
        lines.append(f"   {i}. {t_esc} · <i>{html.escape(cin_s)}</i>{note}")
    lines.append("")
    return lines


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
    for cin, flist in sorted(by_cinema.items(), key=lambda x: x[0].lower()):
        if cin in present or not flist:
            continue
        if cin == "Phenomena":
            notes.append(
                f"<i><b>{html.escape(cin)}</b>: sus sesiones en la web no caen en hoy/mañana "
                f"(suelen ser fechas posteriores).</i>"
            )
        else:
            notes.append(
                f"<i><b>{html.escape(cin)}</b>: no hay sesiones para hoy/mañana con los datos obtenidos.</i>"
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
    day_list = [
        (d0, "Hoy"),
        (d1, "Mañana"),
    ]
    target_dates = {d0, d1}

    # (título, horas, nota HTML opcional)
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

    sections: List[str] = []

    now_str = datetime.now(tz).strftime("%d/%m/%Y %H:%M")
    header_lines: List[str] = [
        "<b>Cartelera — hoy y mañana</b>",
        "",
        f"<i>Barcelona · {html.escape(tz_name)}</i>",
        f"<i>Actualizado {html.escape(now_str)}</i>",
        "<i>Resumen por nota TMDb; luego cartelera por cine (orden: nota, luego sin nota).</i>",
    ]
    if lim.top_films_per_cinema_per_day > 0:
        header_lines.append(
            f"<i>Tope por cine: {lim.top_films_per_cinema_per_day} con ★, "
            f"{lim.extra_unrated_per_cinema_per_day} sin nota (ver DIGEST_TOP_PER_CINEMA).</i>"
        )
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
                "<i>Ninguna sesión con hora en este periodo (según las webs consultadas).</i>"
            )
        else:
            g_lines = _global_top_lines(block, lim.global_top_per_day)
            if g_lines:
                lines.extend(g_lines)
            for cix, cinema in enumerate(sorted(block.keys())):
                if cix:
                    lines.append("")
                lines.append(f"<b>{html.escape(cinema)}</b>")
                orig_count = len(block[cinema])
                raw = block[cinema]
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
                        lines.append(f"   • {t_esc} — {horas}{note}")
                    else:
                        lines.append(f"   • {t_esc}{note}")

                for title, times, rating in show_r:
                    _emit(title, times, rating)
                if show_u:
                    lines.append(
                        "<i>   Sin ★ TMDb (sin match o votos por debajo del mínimo):</i>"
                    )
                    for title, times, rating in show_u:
                        _emit(title, times, rating)
                parts_msg: List[str] = []
                if hide_r:
                    parts_msg.append(
                        f"{hide_r} con ★ TMDb no listadas (tope {top_n}/día por cine)"
                    )
                if hide_u:
                    parts_msg.append(
                        f"{hide_u} sin ★ no listadas (tope {extra_u} sesiones)"
                    )
                if parts_msg:
                    lines.append(f"<i>… {' · '.join(parts_msg)}</i>")
                elif cinema == "Verdi" and max_v > 0 and top_n == 0 and orig_count > max_v:
                    lines.append(
                        "<i>… y más en "
                        '<a href="https://barcelona.cines-verdi.com/es/cartelera">Verdi</a></i>'
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
            "<b>Avisos</b>",
            "<i>Alguna web no se pudo leer bien en esta pasada.</i>",
            "",
        ]
        for f in failures:
            fl.append(f"   • {html.escape(f)}")
        sections.append("\n".join(fl))

    if lim.show_debug_footer:
        sections.append(
            "<i>Debug: GitHub Actions → Run workflow · "
            "local: <code>python src/main.py</code></i>"
        )

    return [s for s in sections if s.strip()]


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
    """Un solo string (p. ej. logs); para Telegram usar build_digest_sections + merge."""
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
        "<b>Novedades</b>",
        "<i>Altas con sesión hoy o mañana; orden por nota TMDb.</i>",
        "",
    ]
    shown = picked[:max_lines]
    for f in shown:
        note = f" {f.rating}" if f.rating else ""
        lines.append(
            f"   • <b>{html.escape(f.cinema)}</b> · {html.escape(f.title)}{note}"
        )
    if len(picked) > max_lines:
        lines.append(f"   <i>… y {len(picked) - max_lines} más</i>")
    return "\n".join(lines)
