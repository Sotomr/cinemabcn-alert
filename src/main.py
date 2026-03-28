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
from tmdb_ratings import enrich_films_with_ratings, sort_films_for_tmdb_priority
from digest import (
    DigestLimits,
    build_digest_sections,
    build_digest_telegram_parts,
    expand_digest_parts_for_telegram,
    film_has_show_in_window,
    format_novelties_html,
    merge_sections_for_telegram,
)
from diff_engine import compute_new_entries
from models import Film, Snapshot
from notifier import TELEGRAM_MAX, send_telegram_messages
from scrapers.espai_texas import EspaiTexasScraper
from scrapers.filmoteca import FilmotecaScraper
from scrapers.girona import GironaScraper
from scrapers.malda import MaldaScraper
from scrapers.phenomena import PhenomenaScraper
from scrapers.renoir import RenoirScraper
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
        FilmotecaScraper(),
        PhenomenaScraper(),
        VerdiScraper(),
        MaldaScraper(),
        ZumzeigScraper(),
        GironaScraper(),
        RenoirScraper(),
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
    films = sort_films_for_tmdb_priority(films, settings.timezone)
    enrich_films_with_ratings(
        films,
        settings.tmdb_api_key,
        data_dir=settings.data_dir,
        max_films=settings.tmdb_max_films,
        min_votes=settings.tmdb_min_votes,
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
        global_top_per_day=settings.digest_global_top,
        top_films_per_cinema_per_day=settings.digest_top_per_cinema,
        extra_unrated_per_cinema_per_day=settings.digest_extra_unrated,
        novelties_top_per_cinema=settings.digest_novelties_top_per_cinema,
        novelties_max_lines=settings.digest_novelties_max_lines,
        only_today=settings.digest_only_today,
    )
    if settings.digest_telegram_by_cinema:
        digest_chunks = build_digest_telegram_parts(
            films,
            failures,
            tz_name=settings.timezone,
            limits=limits,
        )
        sections = expand_digest_parts_for_telegram(
            digest_chunks, max_len=TELEGRAM_MAX - 150
        )
    else:
        sections = merge_sections_for_telegram(
            build_digest_sections(
                films,
                failures,
                tz_name=settings.timezone,
                limits=limits,
            ),
            max_len=TELEGRAM_MAX - 150,
        )

    if settings.append_novelties and not is_first:
        new_entries = compute_new_entries(prev_films, current.films)
        new_entries = [
            f
            for f in new_entries
            if film_has_show_in_window(f, settings.timezone)
        ]
        if new_entries:
            sections.extend(
                merge_sections_for_telegram(
                    [
                        format_novelties_html(
                            new_entries,
                            top_per_cinema=limits.novelties_top_per_cinema,
                            max_lines=limits.novelties_max_lines,
                        )
                    ],
                    max_len=TELEGRAM_MAX - 150,
                )
            )

    if is_first:
        sections.extend(
            merge_sections_for_telegram(
                [
                    "<i>Primera execució: instantània desada. "
                    "Les «novetats» tindran sentit a partir del proper avís.</i>"
                ],
                max_len=TELEGRAM_MAX - 150,
            )
        )

    telegram_parts = sections
    log_text = "\n\n--- missatge següent ---\n\n".join(telegram_parts)

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
