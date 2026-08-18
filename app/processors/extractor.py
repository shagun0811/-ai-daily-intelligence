"""Optional full-article extraction for short RSS snippets. Failures are skipped."""

from __future__ import annotations

from urllib.parse import urlparse

from app.config.logging import STAGE_EXTRACT, get_logger, log_stage
from app.utils.http import HttpError, fetch_url
from app.utils.text import normalize_whitespace

logger = get_logger(__name__)

_SKIP_HOSTS = {
    "arxiv.org",
    "export.arxiv.org",
    "arxiv.org.",
}


def should_extract_full_text(
    *,
    url: str,
    item_kind: str,
    cleaned_text: str | None,
    min_chars: int,
) -> bool:
    if item_kind == "research_paper":
        return False
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if host in _SKIP_HOSTS:
        return False
    return len(cleaned_text or "") < min_chars


def extract_full_text(url: str, *, timeout: int, html: str | None = None) -> str | None:
    """Return extracted article text, or None if extraction fails."""
    import trafilatura

    page = html
    if page is None:
        try:
            page = fetch_url(url, timeout=timeout).text
        except HttpError as exc:
            log_stage(logger, STAGE_EXTRACT, "fetch failed url=%s error=%s", url, exc, level=30)
            return None
    try:
        extracted = trafilatura.extract(
            page,
            include_comments=False,
            include_tables=False,
            url=url,
        )
    except Exception as exc:  # noqa: BLE001 — never fail the pipeline on one page
        log_stage(logger, STAGE_EXTRACT, "trafilatura failed url=%s error=%s", url, exc, level=30)
        return None
    cleaned = normalize_whitespace(extracted)
    return cleaned or None
