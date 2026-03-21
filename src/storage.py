from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from models import Snapshot

logger = logging.getLogger(__name__)


def load_snapshot(path: Path) -> Optional[Snapshot]:
    if not path.is_file():
        logger.info("No hay snapshot previo en %s", path)
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return Snapshot.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("Snapshot corrupto o inválido (%s): se ignora", e)
        return None


def save_snapshot(path: Path, snapshot: Snapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
    logger.info("Snapshot guardado en %s (%s películas)", path, len(snapshot.films))
