from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from models import Film


class BaseScraper(ABC):
    cinema_name: str

    @abstractmethod
    def fetch(self) -> List[Film]:
        raise NotImplementedError
