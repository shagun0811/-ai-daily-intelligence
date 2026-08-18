"""RSS / Atom collector. Uses requests + feedparser; does not scrape HTML unless the feed is empty of links."""

from __future__ import annotations

import feedparser

from app.collectors.base import BaseCollector, CollectedItem, CollectorError
from app.config.logging import STAGE_COLLECT, get_logger, log_stage
from app.database.enums import ItemKind, SourceType
from app.database.models import Source
from app.utils.dates import parse_datetime
from app.utils.http import HttpError, fetch_url
from app.utils.text import normalize_whitespace, strip_html, truncate

logger = get_logger(__name__)


class RssCollector(BaseCollector):
    source_type = SourceType.RSS

    def collect(self, source: Source, *, limit: int, timeout: int) -> list[CollectedItem]:
        try:
            response = fetch_url(source.url, timeout=timeout)
        except HttpError as exc:
            raise CollectorError(str(exc)) from exc

        feed = feedparser.parse(response.text)
        entries = list(getattr(feed, "entries", []) or [])
        if not entries:
            bozo = bool(getattr(feed, "bozo", False))
            detail = getattr(feed, "bozo_exception", None)
            if bozo or not _looks_like_feed(response.text):
                raise CollectorError(f"malformed feed: {detail or 'no RSS/Atom entries'}")
            log_stage(logger, STAGE_COLLECT, "empty feed source=%s", source.name, level=30)
            return []

        items: list[CollectedItem] = []
        for entry in entries:
            item = _item_from_entry(entry)
            if item is None:
                continue
            items.append(item)
            if len(items) >= limit:
                break
        return items


def _looks_like_feed(text: str) -> bool:
    head = text[:4000].lower()
    return "<rss" in head or "<feed" in head or "<rdf:rdf" in head


def _item_from_entry(entry: object) -> CollectedItem | None:
    title = strip_html(str(getattr(entry, "title", "") or ""))
    url = normalize_whitespace(str(getattr(entry, "link", "") or ""))
    if not title or not url:
        return None

    raw = _entry_raw_text(entry)
    cleaned = strip_html(raw) if raw else ""
    description = strip_html(str(getattr(entry, "summary", "") or getattr(entry, "description", "") or ""))
    if not description:
        description = truncate(cleaned, 400) or None

    return CollectedItem(
        title=truncate(title, 1024),
        url=url,
        author=_entry_author(entry),
        published_at=_entry_published(entry),
        description=description or None,
        raw_text=raw or None,
        cleaned_text=cleaned or description or title,
        item_kind=ItemKind.ARTICLE,
    )


def _entry_raw_text(entry: object) -> str:
    content = getattr(entry, "content", None)
    if content:
        parts = []
        for block in content:
            value = block.get("value") if isinstance(block, dict) else getattr(block, "value", "")
            if value:
                parts.append(str(value))
        if parts:
            return "\n".join(parts)
    return str(getattr(entry, "summary", "") or getattr(entry, "description", "") or "")


def _entry_author(entry: object) -> str | None:
    author = normalize_whitespace(str(getattr(entry, "author", "") or ""))
    if author:
        return truncate(author, 512)
    authors = getattr(entry, "authors", None) or []
    names = []
    for item in authors:
        name = item.get("name") if isinstance(item, dict) else getattr(item, "name", "")
        if name:
            names.append(str(name))
    if names:
        return truncate(", ".join(names), 512)
    return None


def _entry_published(entry: object):
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if parsed is not None:
        value = parse_datetime(parsed)
        if value is not None:
            return value
    return parse_datetime(getattr(entry, "published", None) or getattr(entry, "updated", None))
