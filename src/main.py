from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ejecutar desde la raíz del repo: python src/main.py
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from classifiers import classify_film, week_bounds_today
from config import load_settings
from diff_engine import compute_new_entries, titles_for_compare
from models import Film, Snapshot
from notifier import format_alert_html, send_telegram_message
from scrapers.espai_texas import EspaiTexasScraper
from scrapers.malda import MaldaScraper
from scrapers.phenomena import PhenomenaScraper
from scrapers.verdi import VerdiScraper
from scrapers.zumzeig import ZumzeigScraper
from storage import load_snapshot, save_snapshot

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("cinema_alert")


def _run_scrapers() -> tuple[list[Film], list[str]]:
    scrapers = [
        VerdiScraper(),
        PhenomenaScraper(),
        MaldaScraper(),
        ZumzeigScraper(),
        EspaiTexasScraper(),
    ]
    films: list[Film] = []
    failures: list[str] = []
    for sc in scrapers:
        try:
            got = sc.fetch()
            films.extend(got)
        except Exception as e:
            msg = f"{sc.cinema_name}: {e}"
            logger.exception("Scraper falló: %s", sc.cinema_name)
            failures.append(msg)
    return films, failures


def main() -> int:
    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    films, failures = _run_scrapers()
    fetched_at = datetime.now(timezone.utc).isoformat()
    current = Snapshot(fetched_at=fetched_at, films=films)

    prev = load_snapshot(settings.snapshot_path)
    prev_films = list(prev.films) if prev else []
    # Snapshot inicial del repo (1970-01-01) = aún no hay captura real
    is_first = prev is None or prev.fetched_at.startswith("1970-01-01")

    prev_titles_norm = frozenset(titles_for_compare(prev_films))
    week_start, week_end = week_bounds_today()

    if is_first:
        save_snapshot(settings.snapshot_path, current)
        text = format_alert_html({}, failures=failures, first_run=True)
    else:
        new_entries = compute_new_entries(prev_films, current.films)
        grouped: dict[str, list[tuple[Film, str]]] = {}
        for film in new_entries:
            cl = classify_film(
                film,
                previous_titles_norm=prev_titles_norm,
                week_start=week_start,
                week_end=week_end,
            )
            grouped.setdefault(film.cinema, []).append((film, cl.primary))
        save_snapshot(settings.snapshot_path, current)
        text = format_alert_html(grouped, failures=failures, first_run=False)

    if settings.skip_telegram or settings.dry_run or not settings.telegram_bot_token:
        logger.info("Telegram desactivado o sin token. Mensaje generado:\n%s", text)
        if not settings.skip_telegram and not settings.dry_run:
            logger.warning(
                "Define TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID para enviar avisos."
            )
        return 0

    if not settings.telegram_chat_id:
        logger.error("Falta TELEGRAM_CHAT_ID")
        return 1

    try:
        send_telegram_message(
            settings.telegram_bot_token,
            settings.telegram_chat_id,
            text,
        )
    except Exception as e:
        logger.exception("No se pudo enviar Telegram: %s", e)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
