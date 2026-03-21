from __future__ import annotations

import html
import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple
from zoneinfo import ZoneInfo

from models import Film, Show

# Nombres de día en español (lunes=0)
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


def _fmt_day_header(d: date, label: str) -> str:
    wd = _WEEKDAY_ES[d.weekday()]
    mon = _MONTH_ES[d.month - 1]
    return f"{label} — {wd} {d.day} {mon}"


def parse_show_date(show: Show) -> date | None:
    """Interpreta Show.datetime tipo '20260321 20:30' como fecha local del cine."""
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


def format_daily_digest_html(
    films: List[Film],
    failures: List[str],
    *,
    tz_name: str = "Europe/Madrid",
) -> str:
    """
    Mensaje principal: qué hay HOY, MAÑANA y PASADO MAÑANA.
    Los cines con sesiones parseadas (p. ej. Verdi) van por día.
    El resto se lista al final como cartelera sin desglose horario.
    """
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

    now_str = datetime.now(tz).strftime("%d/%m/%Y %H:%M")
    lines: List[str] = [
        "🎬 <b>Cartelera — próximos 3 días</b>",
        f"<i>Barcelona · {html.escape(tz_name)} · {html.escape(now_str)}</i>",
        "",
    ]

    # Por cada día: cine -> lista de (título, lista de horas únicas ordenadas)
    by_day_cinema: Dict[date, Dict[str, List[Tuple[str, List[str]]]]] = {
        d: {} for d, _ in day_list
    }

    # Películas sin ninguna sesión parseada (Maldà, Texas, etc.)
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
            # Tiene shows pero ninguno cae en la ventana de 3 días
            no_schedule.setdefault(film.cinema, []).append(film)
            continue

        for sd, times in by_date.items():
            times_u = sorted(set(times))
            title = film.title
            cin = film.cinema
            lst = by_day_cinema.setdefault(sd, {}).setdefault(cin, [])
            # Unir misma película si aparece duplicada
            found = False
            for i, (t, hs) in enumerate(lst):
                if t == title:
                    merged = sorted(set(hs + times_u))
                    lst[i] = (t, merged)
                    found = True
                    break
            if not found:
                lst.append((title, times_u))

    # Cabeceras por día
    for d, lab in day_list:
        lines.append(f"📅 <b>{html.escape(_fmt_day_header(d, lab))}</b>")
        block = by_day_cinema.get(d, {})
        if not block:
            lines.append("<i>Nada con horario detectado para este día en las fuentes con sesiones.</i>")
        else:
            for cinema in sorted(block.keys()):
                lines.append(f"<b>{html.escape(cinema)}</b>")
                for title, times in sorted(block[cinema], key=lambda x: x[0].lower()):
                    t_esc = html.escape(title)
                    if times:
                        horas = ", ".join(html.escape(x) for x in times)
                        lines.append(f"  • {t_esc} — {horas}")
                    else:
                        lines.append(f"  • {t_esc}")
                lines.append("")

    # Cartelera sin desglose por día
    lines.append("—")
    lines.append("<b>Cartelera (sin horarios en este mensaje)</b>")
    lines.append(
        "<i>Estos cines no publican sesiones en el formato que leemos aquí; "
        "revisa la web para horas exactas.</i>"
    )
    if not no_schedule:
        lines.append("<i>Nada que listar aquí.</i>")
    else:
        for cinema in sorted(no_schedule.keys()):
            lines.append(f"<b>{html.escape(cinema)}</b>")
            seen_t: set[str] = set()
            for film in no_schedule[cinema]:
                if film.title in seen_t:
                    continue
                seen_t.add(film.title)
                if film.url:
                    lines.append(
                        f"  • {html.escape(film.title)} — "
                        f'<a href="{html.escape(film.url)}">web</a>'
                    )
                else:
                    lines.append(f"  • {html.escape(film.title)}")
            lines.append("")

    if failures:
        lines.append("<b>Scrapers con error</b>")
        for f in failures:
            lines.append(f"  • {html.escape(f)}")
        lines.append("")

    lines.append(
        "<i>Prueba manual: GitHub → Actions → Run workflow · "
        "Local: <code>python src/main.py</code></i>"
    )

    return "\n".join(lines).strip()


def format_novelties_html(films: List[Film], *, limit: int = 15) -> str:
    if not films:
        return ""
    lines = [
        "",
        "<b>Novedades desde la última ejecución</b>",
        "<i>(cambios detectados respecto al snapshot anterior)</i>",
    ]
    for f in films[:limit]:
        lines.append(
            f"  • <b>{html.escape(f.cinema)}</b>: {html.escape(f.title)}"
        )
    if len(films) > limit:
        lines.append(f"  <i>… y {len(films) - limit} más</i>")
    return "\n".join(lines)
