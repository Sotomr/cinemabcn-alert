from __future__ import annotations

import html
import logging
from typing import Iterable, List

import requests

from classifiers import (
    PRIMARY_NEW_ON_BOARD,
    PRIMARY_RELEASE_WEEK,
    PRIMARY_SPECIAL_EVENT,
)
from models import Film

logger = logging.getLogger(__name__)

TELEGRAM_MAX = 3900  # margen bajo el límite 4096

_LABEL = {
    PRIMARY_RELEASE_WEEK: "Estreno",
    PRIMARY_NEW_ON_BOARD: "Nueva",
    PRIMARY_SPECIAL_EVENT: "Especial",
}


def send_telegram_message(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for chunk in _chunk_text(text, TELEGRAM_MAX):
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        r = requests.post(url, json=payload, timeout=30)
        r.raise_for_status()
        logger.info("Mensaje Telegram enviado (%s caracteres)", len(chunk))


def _chunk_text(text: str, max_len: int) -> List[str]:
    text = text.strip()
    if len(text) <= max_len:
        return [text]
    parts: List[str] = []
    rest = text
    while rest:
        if len(rest) <= max_len:
            parts.append(rest)
            break
        cut = rest.rfind("\n", 0, max_len)
        if cut < max_len // 2:
            cut = max_len
        parts.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    return parts


def format_alert_html(
    grouped: dict[str, list[tuple[Film, str]]],
    *,
    failures: list[str],
    first_run: bool,
) -> str:
    lines: List[str] = [
        "🎬 <b>Alertas cinéfilas en Barcelona</b>",
        "",
    ]
    if first_run:
        lines.extend(
            [
                "<i>Primera ejecución: snapshot creado. "
                "Las próximas corridas avisarán solo de novedades.</i>",
                "",
            ]
        )

    if not first_run and not grouped and not failures:
        lines.append("Sin novedades destacadas esta vez.")
    else:
        for cinema in sorted(grouped.keys()):
            lines.append(f"<b>{html.escape(cinema)}</b>")
            for film, primary in grouped[cinema]:
                label = _LABEL.get(primary, primary)
                title = html.escape(film.title)
                lines.append(f"  • [{label}] {title}")
            lines.append("")

    if failures:
        lines.append("<b>Scrapers con error</b>")
        for f in failures:
            lines.append(f"  • {html.escape(f)}")
    return "\n".join(lines).strip()
