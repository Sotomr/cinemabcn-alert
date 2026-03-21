from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from models import Film, Show

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
        elif cin == "Moby Balmes":
            notes.append(
                f"<i><b>{html.escape(cin)}</b>: la web no publica horarios en la página que usamos; "
                f"consulta la cartelera en moobycinemas.com.</i>"
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
    header = "\n".join(
        [
            "🎬 <b>Cartelera — hoy y mañana</b>",
            "",
            f"<i>📍 Barcelona · {html.escape(tz_name)}</i>",
            f"<i>🕐 Actualizado {html.escape(now_str)}</i>",
            "",
            _SEP,
        ]
    )
    sections.append(header)

    # Un bloque por día
    for idx, (d, lab) in enumerate(day_list):
        lines: List[str] = [
            f"📅 <b>{html.escape(_fmt_day_header(d, lab))}</b>",
            "",
        ]
        block = by_day_cinema.get(d, {})
        if not block:
            lines.append(
                "<i>Ninguna sesión con hora en este periodo (según las webs consultadas).</i>"
            )
        else:
            for cix, cinema in enumerate(sorted(block.keys())):
                if cix:
                    lines.append("")
                lines.append(f"<b>{html.escape(cinema)}</b>")
                rows = sorted(block[cinema], key=lambda x: x[0].lower())
                max_v = lim.max_films_verdi_per_day
                truncated = False
                if max_v > 0 and len(rows) > max_v:
                    rows = rows[:max_v]
                    truncated = True
                for title, times, rating in rows:
                    t_esc = html.escape(title)
                    note = f" {rating}" if rating else ""
                    if times:
                        horas = ", ".join(html.escape(x) for x in times)
                        lines.append(f"   • {t_esc} — {horas}{note}")
                    else:
                        lines.append(f"   • {t_esc}{note}")
                if truncated:
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
            "<b>⚠️ Avisos</b>",
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


def format_novelties_html(films: List[Film], *, limit: int = 12) -> str:
    if not films:
        return ""
    lines = [
        _SEP,
        "<b>✨ Novedades</b>",
        "<i>Respecto al último aviso (altas en cartelera).</i>",
        "",
    ]
    for f in films[:limit]:
        note = f" {f.rating}" if f.rating else ""
        lines.append(
            f"   • <b>{html.escape(f.cinema)}</b> · {html.escape(f.title)}{note}"
        )
    if len(films) > limit:
        lines.append(f"   <i>… y {len(films) - limit} más</i>")
    return "\n".join(lines)
