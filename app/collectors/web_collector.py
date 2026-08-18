"""Webpage collector. Used only when a source has no RSS/API. Extracts article text with trafilatura."""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.collectors.base import BaseCollector, CollectedItem, CollectorError
from app.config.logging import STAGE_EXTRACT, get_logger, log_stage
from app.database.enums import ItemKind, SourceType
from app.database.models import Source
from app.utils.dates import parse_datetime
from app.utils.http import HttpError, fetch_url
from app.utils.text import normalize_whitespace, strip_html, truncate

logger = get_logger(__name__)


class WebCollector(BaseCollector):
    source_type = SourceType.WEBPAGE

    def collect(self, source: Source, *, limit: int, timeout: int) -> list[CollectedItem]:
        extra = source.extra_config or {}
        selector = extra.get("link_selector")
        urls = [source.url]
        if selector:
            urls = _listing_urls(source.url, selector, limit=limit, timeout=timeout)

        items: list[CollectedItem] = []
        errors: list[str] = []
        for url in urls[:limit]:
            try:
                item = _extract_article(url, timeout=timeout)
            except CollectorError as exc:
                errors.append(str(exc))
                log_stage(logger, STAGE_EXTRACT, "page failed url=%s error=%s", url, exc, level=30)
                continue
            if item is not None:
                items.append(item)

        if not items:
            raise CollectorError("; ".join(errors) if errors else f"no articles extracted from {source.url}")
        return items


def _listing_urls(list_url: str, selector: str, *, limit: int, timeout: int) -> list[str]:
    try:
        response = fetch_url(list_url, timeout=timeout)
    except HttpError as exc:
        raise CollectorError(str(exc)) from exc
    soup = BeautifulSoup(response.text, "lxml")
    found: list[str] = []
    for node in soup.select(selector):
        href = node.get("href") if node.name == "a" else None
        if href is None and node.name != "a":
            child = node.find("a")
            href = child.get("href") if child else None
        if not href:
            continue
        absolute = urljoin(list_url, str(href))
        if absolute not in found:
            found.append(absolute)
        if len(found) >= limit:
            break
    if not found:
        raise CollectorError(f"link_selector matched no links: {selector}")
    return found


def _extract_article(url: str, *, timeout: int) -> CollectedItem | None:
    import trafilatura

    try:
        response = fetch_url(url, timeout=timeout)
    except HttpError as exc:
        raise CollectorError(str(exc)) from exc

    extracted = trafilatura.extract(
        response.text,
        include_comments=False,
        include_tables=False,
        url=url,
    )
    if not extracted or not extracted.strip():
        raise CollectorError(f"trafilatura extracted no article text from {url}")

    metadata = trafilatura.extract_metadata(response.text) if hasattr(trafilatura, "extract_metadata") else None
    title = ""
    author = None
    published = None
    if metadata is not None:
        title = normalize_whitespace(getattr(metadata, "title", "") or "")
        author = normalize_whitespace(getattr(metadata, "author", "") or "") or None
        published = parse_datetime(getattr(metadata, "date", None))
    if not title:
        soup = BeautifulSoup(response.text, "lxml")
        if soup.title and soup.title.string:
            title = normalize_whitespace(soup.title.string)
    if not title:
        title = truncate(extracted.splitlines()[0], 1024)

    cleaned = normalize_whitespace(extracted)
    return CollectedItem(
        title=truncate(title, 1024),
        url=url,
        author=truncate(author, 512) if author else None,
        published_at=published,
        description=truncate(cleaned, 400),
        raw_text=extracted,
        cleaned_text=cleaned,
        item_kind=ItemKind.ARTICLE,
    )
