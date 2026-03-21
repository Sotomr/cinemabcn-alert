from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ejecutar desde la raíz del repo: python src/main.py
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import load_settings
from tmdb_ratings import enrich_films_with_ratings
from digest import (
    DigestLimits,
    build_digest_sections,
    format_novelties_html,
    merge_sections_for_telegram,
)
from diff_engine import compute_new_entries
from models import Film, Snapshot
from notifier import TELEGRAM_MAX, send_telegram_messages
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
    enrich_films_with_ratings(
        films,
        settings.tmdb_api_key,
        data_dir=settings.data_dir,
        max_films=settings.tmdb_max_films,
    )
    fetched_at = datetime.now(timezone.utc).isoformat()
    current = Snapshot(fetched_at=fetched_at, films=films)

    prev = load_snapshot(settings.snapshot_path)
    prev_films = list(prev.films) if prev else []
    is_first = prev is None or prev.fetched_at.startswith("1970-01-01")

    limits = DigestLimits(
        max_films_unscheduled_per_cinema=settings.digest_max_unscheduled,
        max_films_verdi_per_day=settings.digest_max_verdi_per_day,
        show_debug_footer=settings.debug_footer,
    )
    sections = build_digest_sections(
        films,
        failures,
        tz_name=settings.timezone,
        limits=limits,
    )

    if settings.append_novelties and not is_first:
        new_entries = compute_new_entries(prev_films, current.films)
        if new_entries:
            sections.append(format_novelties_html(new_entries))

    if is_first:
        sections.append(
            "<i>Primera ejecución: snapshot guardado en el repo. "
            "El bloque «novedades» tendrá más sentido en las siguientes corridas.</i>"
        )

    telegram_parts = merge_sections_for_telegram(sections, max_len=TELEGRAM_MAX - 150)
    log_text = "\n\n--- mensaje siguiente ---\n\n".join(telegram_parts)

    save_snapshot(settings.snapshot_path, current)

    if settings.skip_telegram or settings.dry_run or not settings.telegram_bot_token:
        logger.info("Telegram desactivado o sin token. Mensaje generado:\n%s", log_text)
        if not settings.skip_telegram and not settings.dry_run:
            logger.warning(
                "Define TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID para enviar avisos."
            )
        return 0

    if not settings.telegram_chat_id:
        logger.error("Falta TELEGRAM_CHAT_ID")
        return 1

    try:
        send_telegram_messages(
            settings.telegram_bot_token,
            settings.telegram_chat_id,
            telegram_parts,
        )
    except Exception as e:
        logger.exception("No se pudo enviar Telegram: %s", e)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
