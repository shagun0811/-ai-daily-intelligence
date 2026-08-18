"""RSS parsing tests. Uses fixture XML — no live websites."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.collectors.rss_collector import RssCollector
from app.database.models import Source
from app.utils.dates import parse_datetime
from app.utils.http import HttpError, HttpResponse
from app.utils.text import strip_html

FIXTURES = Path(__file__).parent / "fixtures"


def _source() -> Source:
    return Source(
        id=1,
        name="Mock RSS",
        url="https://blog.example.com/rss",
        type="rss",
        category="company",
        credibility_tier="tier_1",
        enabled=True,
        collection_method="rss",
        extra_config={},
    )


def test_rss_parses_title_url_author_and_date(monkeypatch: pytest.MonkeyPatch) -> None:
    xml = (FIXTURES / "rss_sample.xml").read_text(encoding="utf-8")
    monkeypatch.setattr(
        "app.collectors.rss_collector.fetch_url",
        lambda url, timeout=20: HttpResponse(url=url, status_code=200, text=xml, elapsed_ms=1),
    )
    items = RssCollector().collect(_source(), limit=40, timeout=20)
    assert len(items) == 2
    first = items[0]
    assert first.title == "New open-source LLM released"
    assert first.url == "https://blog.example.com/llm-release"
    assert first.author == "Ada Researcher"
    assert first.published_at is not None
    assert first.published_at.year == 2026
    assert "8B parameter" in (first.cleaned_text or "")
    assert "<b>" not in (first.cleaned_text or "")
    assert items[1].published_at is None


def test_rss_skips_empty_title_and_missing_link(monkeypatch: pytest.MonkeyPatch) -> None:
    xml = (FIXTURES / "rss_sample.xml").read_text(encoding="utf-8")
    monkeypatch.setattr(
        "app.collectors.rss_collector.fetch_url",
        lambda url, timeout=20: HttpResponse(url=url, status_code=200, text=xml, elapsed_ms=1),
    )
    items = RssCollector().collect(_source(), limit=40, timeout=20)
    urls = {item.url for item in items}
    assert "https://blog.example.com/empty-title" not in urls
    assert all(item.url for item in items)


def test_rss_malformed_feed_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.collectors.base import CollectorError

    monkeypatch.setattr(
        "app.collectors.rss_collector.fetch_url",
        lambda url, timeout=20: HttpResponse(
            url=url, status_code=200, text="<html>not a feed</html>", elapsed_ms=1
        ),
    )
    with pytest.raises(CollectorError):
        RssCollector().collect(_source(), limit=10, timeout=20)


def test_rss_http_error_becomes_collector_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.collectors.base import CollectorError

    def _fail(url: str, timeout: int = 20) -> HttpResponse:
        raise HttpError("HTTP 503", status_code=503, url=url)

    monkeypatch.setattr("app.collectors.rss_collector.fetch_url", _fail)
    with pytest.raises(CollectorError):
        RssCollector().collect(_source(), limit=10, timeout=20)


def test_rss_respects_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    xml = (FIXTURES / "rss_sample.xml").read_text(encoding="utf-8")
    monkeypatch.setattr(
        "app.collectors.rss_collector.fetch_url",
        lambda url, timeout=20: HttpResponse(url=url, status_code=200, text=xml, elapsed_ms=1),
    )
    items = RssCollector().collect(_source(), limit=1, timeout=20)
    assert len(items) == 1


def test_strip_html_removes_tags() -> None:
    assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"


def test_parse_datetime_accepts_rfc822_and_invalid() -> None:
    parsed = parse_datetime("Thu, 13 Aug 2026 16:45:00 +0000")
    assert parsed is not None
    assert parsed.day == 13
    assert parse_datetime(None) is None
    assert parse_datetime("not a date at all ###") is None
