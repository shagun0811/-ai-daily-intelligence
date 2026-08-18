"""Shared collector types. Collectors fetch and parse; they do not call an LLM."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.database.enums import ItemKind, SourceType
from app.database.models import Source


class CollectorError(Exception):
    """A single source failed. The manager continues with other sources."""


@dataclass
class CollectedItem:
    title: str
    url: str
    author: str | None = None
    published_at: datetime | None = None
    description: str | None = None
    raw_text: str | None = None
    cleaned_text: str | None = None
    item_kind: ItemKind = ItemKind.ARTICLE
    extra: dict[str, Any] = field(default_factory=dict)


class BaseCollector(ABC):
    source_type: SourceType

    @abstractmethod
    def collect(self, source: Source, *, limit: int, timeout: int) -> list[CollectedItem]:
        """Fetch and parse items. Raise CollectorError if the source cannot be read."""
