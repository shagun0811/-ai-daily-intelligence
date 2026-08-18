"""Webpage extraction tests. Uses local HTML — no live websites."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.collectors.web_collector import WebCollector
from app.database.models import Source
from app.utils.http import HttpResponse

FIXTURES = Path(__file__).parent / "fixtures"


def _source(url: str = "https://example.com/ai-announcement") -> Source:
    return Source(
        id=3,
        name="Mock webpage",
        url=url,
        type="webpage",
        category="company",
        credibility_tier="tier_2",
        enabled=True,
        collection_method="webpage",
        extra_config={},
    )


def test_web_extracts_article_text(monkeypatch: pytest.MonkeyPatch) -> None:
    html = (FIXTURES / "article.html").read_text(encoding="utf-8")
    monkeypatch.setattr(
        "app.collectors.web_collector.fetch_url",
        lambda url, timeout=20: HttpResponse(url=url, status_code=200, text=html, elapsed_ms=2),
    )
    items = WebCollector().collect(_source(), limit=5, timeout=20)
    assert len(items) == 1
    item = items[0]
    assert "multimodal" in item.title.lower() or "multimodal" in (item.cleaned_text or "").lower()
    assert "Cookie banner" not in (item.cleaned_text or "")
    assert "<p>" not in (item.cleaned_text or "")
    assert item.url == "https://example.com/ai-announcement"


def test_web_empty_html_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.collectors.base import CollectorError

    monkeypatch.setattr(
        "app.collectors.web_collector.fetch_url",
        lambda url, timeout=20: HttpResponse(
            url=url, status_code=200, text="<html><body></body></html>", elapsed_ms=1
        ),
    )
    with pytest.raises(CollectorError):
        WebCollector().collect(_source(), limit=1, timeout=20)
