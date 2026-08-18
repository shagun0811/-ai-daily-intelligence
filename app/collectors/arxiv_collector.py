"""arXiv Atom API collector. Stores papers as research items, not generic news."""

from __future__ import annotations

import re
from urllib.parse import urlencode

import feedparser

from app.collectors.base import BaseCollector, CollectedItem, CollectorError
from app.config.logging import STAGE_COLLECT, get_logger, log_stage
from app.database.enums import ItemKind, SourceType
from app.database.models import Source
from app.utils.dates import parse_datetime
from app.utils.http import HttpError, fetch_url
from app.utils.text import normalize_whitespace, strip_html, truncate

logger = get_logger(__name__)

_ARXIV_ID_RE = re.compile(r"arxiv\.org/abs/([^/\s]+)", re.IGNORECASE)


class ArxivCollector(BaseCollector):
    source_type = SourceType.ARXIV

    def collect(self, source: Source, *, limit: int, timeout: int) -> list[CollectedItem]:
        extra = source.extra_config or {}
        categories = extra.get("categories") or ["cs.AI"]
        max_results = min(int(extra.get("max_results") or limit), limit)
        query = " OR ".join(f"cat:{category}" for category in categories)
        params = {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": extra.get("sort_by") or "submittedDate",
            "sortOrder": extra.get("sort_order") or "descending",
        }
        url = f"{source.url}?{urlencode(params)}"
        try:
            response = fetch_url(url, timeout=timeout)
        except HttpError as exc:
            raise CollectorError(str(exc)) from exc

        feed = feedparser.parse(response.text)
        entries = list(getattr(feed, "entries", []) or [])
        if not entries and bool(getattr(feed, "bozo", False)):
            raise CollectorError(f"malformed arXiv feed: {getattr(feed, 'bozo_exception', 'parse error')}")
        if not entries:
            log_stage(logger, STAGE_COLLECT, "empty arXiv result source=%s", source.name, level=30)
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


def _item_from_entry(entry: object) -> CollectedItem | None:
    title = strip_html(str(getattr(entry, "title", "") or ""))
    arxiv_id = _arxiv_id(entry)
    if not title or not arxiv_id:
        return None

    url = f"https://arxiv.org/abs/{_strip_version(arxiv_id)}"
    abstract = strip_html(str(getattr(entry, "summary", "") or ""))
    authors = _authors(entry)
    categories = _categories(entry)
    author = ", ".join(authors) if authors else None

    return CollectedItem(
        title=truncate(normalize_whitespace(title), 1024),
        url=url,
        author=truncate(author, 512) if author else None,
        published_at=parse_datetime(
            getattr(entry, "published_parsed", None) or getattr(entry, "published", None)
        ),
        description=truncate(abstract, 800) or None,
        raw_text=abstract or None,
        cleaned_text=abstract or title,
        item_kind=ItemKind.RESEARCH_PAPER,
        extra={
            "arxiv_id": _strip_version(arxiv_id),
            "abstract": abstract,
            "authors": authors,
            "categories": categories,
            "pdf_url": _pdf_url(entry, arxiv_id),
        },
    )


def _arxiv_id(entry: object) -> str | None:
    entry_id = str(getattr(entry, "id", "") or "")
    match = _ARXIV_ID_RE.search(entry_id)
    if match:
        return match.group(1)
    if entry_id.startswith("http"):
        return None
    return entry_id or None


def _strip_version(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", arxiv_id)


def _authors(entry: object) -> list[str]:
    names: list[str] = []
    for item in getattr(entry, "authors", None) or []:
        name = item.get("name") if isinstance(item, dict) else getattr(item, "name", "")
        if name:
            names.append(normalize_whitespace(str(name)))
    if not names:
        author = normalize_whitespace(str(getattr(entry, "author", "") or ""))
        if author:
            names.append(author)
    return names


def _categories(entry: object) -> list[str]:
    terms: list[str] = []
    for tag in getattr(entry, "tags", None) or []:
        term = tag.get("term") if isinstance(tag, dict) else getattr(tag, "term", "")
        if term:
            terms.append(str(term))
    return terms


def _pdf_url(entry: object, arxiv_id: str) -> str:
    for link in getattr(entry, "links", None) or []:
        href = link.get("href") if isinstance(link, dict) else getattr(link, "href", "")
        link_type = link.get("type") if isinstance(link, dict) else getattr(link, "type", "")
        if link_type == "application/pdf" and href:
            return str(href)
        title = link.get("title") if isinstance(link, dict) else getattr(link, "title", "")
        if title == "pdf" and href:
            return str(href)
    return f"https://arxiv.org/pdf/{_strip_version(arxiv_id)}.pdf"
