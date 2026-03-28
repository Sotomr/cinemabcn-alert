from __future__ import annotations

import logging
import re
from typing import List

from models import Film, Show

from .base import BaseScraper

logger = logging.getLogger(__name__)

CARTELERA_URL = "https://www.cinemesgirona.cat/cartelera"


class GironaScraper(BaseScraper):
    cinema_name = "Cinemes Girona"

    def fetch(self) -> List[Film]:
        from utils import fetch_soup

        soup = fetch_soup(CARTELERA_URL)
        films: List[Film] = []
        seen_titles: dict[str, Film] = {}

        for article in soup.select("article.article-cartelera"):
            h2 = article.select_one("h2 a[data-titulo]") or article.select_one("h2 a")
            if not h2:
                continue
            title = (
                h2.get("data-titulo", "").strip() or h2.get_text(strip=True)
            )
            if not title or len(title) < 2:
                continue

            href = h2.get("href", "")
            url = f"https://www.cinemesgirona.cat{href}" if href and not href.startswith("http") else href

            shows: List[Show] = []
            seen_dt: set[str] = set()
            for a in article.select(".pelicula a[title]"):
                raw = a.get("title", "").strip()
                m = re.match(r"^(\d{8})\s+(\d{2}:\d{2})$", raw)
                if m:
                    dt_str = f"{m.group(1)} {m.group(2)}"
                    if dt_str not in seen_dt:
                        seen_dt.add(dt_str)
                        shows.append(Show(datetime=dt_str))

            lang_spans = article.select(".pelicula span")
            language = ""
            for sp in lang_spans:
                t = sp.get_text(strip=True).upper()
                if t in ("VOSE", "VO", "VOSC", "CASTELLÀ", "CATALÀ"):
                    language = t
                    break
            if language and language in ("VOSE", "VO", "VOSC"):
                for sh in shows:
                    sh.language = language

            norm_key = title.strip().lower()
            if norm_key in seen_titles:
                existing = seen_titles[norm_key]
                existing_dts = {s.datetime for s in existing.shows}
                for s in shows:
                    if s.datetime not in existing_dts:
                        existing.shows.append(s)
                continue

            film = Film(
                cinema=self.cinema_name,
                title=title,
                url=url,
                source_section="cartelera",
                shows=shows,
                labels=[],
            )
            films.append(film)
            seen_titles[norm_key] = film

        logger.info("Cinemes Girona: %s películas", len(films))
        return films
