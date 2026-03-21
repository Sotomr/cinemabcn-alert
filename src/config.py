from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    data_dir: Path
    snapshot_path: Path
    skip_telegram: bool
    dry_run: bool
    timezone: str
    append_novelties: bool
    digest_max_unscheduled: int
    digest_max_verdi_per_day: int
    debug_footer: bool

    # Optional overrides for fragile cinema URLs (see README)
    phenomena_base_url: str | None
    zumzeig_cartelera_url: str | None


def _int_env(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or str(v).strip() == "":
        return default
    try:
        return int(v)
    except ValueError:
        return default


def load_settings() -> Settings:
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "data"
    token = os.getenv("TELEGRAM_BOT_TOKEN") or None
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or None
    skip = os.getenv("SKIP_TELEGRAM", "").lower() in ("1", "true", "yes")
    dry = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")
    tz = os.getenv("TIMEZONE", "Europe/Madrid").strip() or "Europe/Madrid"
    append_n = os.getenv("APPEND_NOVELTIES", "1").lower() not in ("0", "false", "no")
    dbg = os.getenv("DEBUG_FOOTER", "").lower() in ("1", "true", "yes")

    return Settings(
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
        data_dir=data_dir,
        snapshot_path=data_dir / "latest_snapshot.json",
        skip_telegram=skip,
        dry_run=dry,
        timezone=tz,
        append_novelties=append_n,
        digest_max_unscheduled=_int_env("DIGEST_MAX_UNSCHEDULED", 15),
        digest_max_verdi_per_day=_int_env("DIGEST_MAX_VERDI_PER_DAY", 0),
        debug_footer=dbg,
        phenomena_base_url=os.getenv("PHENOMENA_BASE_URL") or None,
        zumzeig_cartelera_url=os.getenv("ZUMZEIG_CARTELERA_URL") or None,
    )
