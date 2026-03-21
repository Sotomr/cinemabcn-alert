from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple
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


@dataclass(frozen=True)
class DigestLimits:
    """Límites para que el mensaje sea legible en Telegram."""

    max_films_unscheduled_per_cinema: int = 15
    max_films_verdi_per_day: int = 0  # 0 = sin límite
    show_debug_footer: bool = False


def _fmt_day_header(d: date, label: str) -> str:
    wd = _WEEKDAY_ES[d.weekday()]
    mon = _MONTH_ES[d.month - 1]
    return f"{label} — {wd} {d.day} {mon}"


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


def three_calendar_days(tz: ZoneInfo) -> Tuple[date, date, date]:
    today = datetime.now(tz).date()
    return today, today + timedelta(days=1), today + timedelta(days=2)


def _dedupe_films_by_title(films: List[Film]) -> List[Film]:
    seen: set[str] = set()
    out: List[Film] = []
    for f in films:
        k = f.title.strip().lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(f)
    return out


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

    d0, d1, d2 = three_calendar_days(tz)
    day_list = [
        (d0, "Hoy"),
        (d1, "Mañana"),
        (d2, "Pasado mañana"),
    ]
    target_dates = {d0, d1, d2}

    by_day_cinema: Dict[date, Dict[str, List[Tuple[str, List[str]]]]] = {
        d: {} for d, _ in day_list
    }
    no_schedule: Dict[str, List[Film]] = {}

    for film in films:
        if not film.shows:
            no_schedule.setdefault(film.cinema, []).append(film)
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
            no_schedule.setdefault(film.cinema, []).append(film)
            continue

        for sd, times in by_date.items():
            times_u = sorted(set(times))
            title = film.title
            cin = film.cinema
            lst = by_day_cinema.setdefault(sd, {}).setdefault(cin, [])
            found = False
            for i, (t, hs) in enumerate(lst):
                if t == title:
                    merged = sorted(set(hs + times_u))
                    lst[i] = (t, merged)
                    found = True
                    break
            if not found:
                lst.append((title, times_u))

    sections: List[str] = []

    now_str = datetime.now(tz).strftime("%d/%m/%Y %H:%M")
    header = "\n".join(
        [
            "🎬 <b>Cartelera — próximos 3 días</b>",
            f"<i>Barcelona · {html.escape(tz_name)} · {html.escape(now_str)}</i>",
        ]
    )
    sections.append(header)

    # Un bloque por día (horarios Verdi / otros con sesiones)
    for d, lab in day_list:
        lines: List[str] = [
            f"📅 <b>{html.escape(_fmt_day_header(d, lab))}</b>",
        ]
        block = by_day_cinema.get(d, {})
        if not block:
            lines.append(
                "<i>Nada con horario en fuentes con sesiones para este día.</i>"
            )
        else:
            for cinema in sorted(block.keys()):
                lines.append(f"<b>{html.escape(cinema)}</b>")
                rows = sorted(block[cinema], key=lambda x: x[0].lower())
                max_v = lim.max_films_verdi_per_day
                truncated = False
                if max_v > 0 and len(rows) > max_v:
                    rows = rows[:max_v]
                    truncated = True
                for title, times in rows:
                    t_esc = html.escape(title)
                    if times:
                        horas = ", ".join(html.escape(x) for x in times)
                        lines.append(f"  • {t_esc} — {horas}")
                    else:
                        lines.append(f"  • {t_esc}")
                if truncated:
                    lines.append(
                        f"<i>… y más títulos este día — "
                        f'<a href="https://barcelona.cines-verdi.com/es/cartelera">cartelera Verdi</a></i>'
                    )
                lines.append("")
        sections.append("\n".join(lines).strip())

    # Cartelera sin horario: un bloque por cine (listas largas recortadas)
    footer_intro = "\n".join(
        [
            "────────────",
            "<b>Otras carteleras</b> (sin horas en este aviso)",
            "<i>Enlaces a la web del cine para sesiones exactas.</i>",
        ]
    )
    sections.append(footer_intro)

    if not no_schedule:
        sections.append("<i>No hay listados sin sesiones parseadas.</i>")
    else:
        # Orden: cines con menos ruido primero
        order_pref = (
            "Espai Texas",
            "Phenomena",
            "Zumzeig",
            "Maldà",
            "Verdi",
        )

        def _cin_sort(name: str) -> tuple[int, str]:
            try:
                return (order_pref.index(name), name.lower())
            except ValueError:
                return (99, name.lower())

        for cinema in sorted(no_schedule.keys(), key=_cin_sort):
            raw = _dedupe_films_by_title(no_schedule[cinema])
            raw.sort(key=lambda f: f.title.lower())
            max_f = lim.max_films_unscheduled_per_cinema
            show = raw[:max_f] if max_f > 0 else raw
            rest = len(raw) - len(show)

            lines = [f"<b>{html.escape(cinema)}</b>"]
            for film in show:
                if film.url:
                    lines.append(
                        f"  • {html.escape(film.title)} — "
                        f'<a href="{html.escape(film.url)}">web</a>'
                    )
                else:
                    lines.append(f"  • {html.escape(film.title)}")
            if rest > 0:
                lines.append(
                    f"<i>… y {rest} títulos más (lista completa en la web del cine)</i>"
                )
            sections.append("\n".join(lines))

    if failures:
        fl = ["<b>Scrapers con error</b>"]
        for f in failures:
            fl.append(f"  • {html.escape(f)}")
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
        "────────────",
        "<b>Novedades desde la última ejecución</b>",
        "<i>Diff respecto al snapshot anterior (puede solaparse con lo de arriba).</i>",
    ]
    for f in films[:limit]:
        lines.append(
            f"  • <b>{html.escape(f.cinema)}</b>: {html.escape(f.title)}"
        )
    if len(films) > limit:
        lines.append(f"  <i>… y {len(films) - limit} más</i>")
    return "\n".join(lines)
