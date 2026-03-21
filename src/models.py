from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class Show:
    datetime: str
    room: Optional[str] = None
    language: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "datetime": self.datetime,
            "room": self.room,
            "language": self.language,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Show":
        return Show(
            datetime=d["datetime"],
            room=d.get("room"),
            language=d.get("language"),
        )


@dataclass
class Film:
    cinema: str
    title: str
    url: str
    source_section: str
    shows: List[Show] = field(default_factory=list)
    labels: List[str] = field(default_factory=list)
    # Nota corta p. ej. "★ 7.4 TMDb" (opcional, desde API)
    rating: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cinema": self.cinema,
            "title": self.title,
            "url": self.url,
            "source_section": self.source_section,
            "shows": [s.to_dict() for s in self.shows],
            "labels": list(self.labels),
            "rating": self.rating,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Film":
        shows_raw = d.get("shows") or []
        return Film(
            cinema=d["cinema"],
            title=d["title"],
            url=d.get("url", ""),
            source_section=d.get("source_section", ""),
            shows=[Show.from_dict(s) for s in shows_raw],
            labels=list(d.get("labels") or []),
            rating=d.get("rating"),
        )


@dataclass
class Snapshot:
    fetched_at: str
    films: List[Film]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fetched_at": self.fetched_at,
            "films": [f.to_dict() for f in self.films],
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Snapshot":
        films_raw = d.get("films") or []
        return Snapshot(
            fetched_at=d["fetched_at"],
            films=[Film.from_dict(f) for f in films_raw],
        )
