"""arXiv collector tests. Uses fixture Atom XML — no live API calls."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.collectors.arxiv_collector import ArxivCollector
from app.database.enums import ItemKind
from app.database.models import Source
from app.utils.http import HttpResponse

FIXTURES = Path(__file__).parent / "fixtures"


def _source() -> Source:
    return Source(
        id=2,
        name="Mock arXiv",
        url="https://export.arxiv.org/api/query",
        type="arxiv",
        category="research",
        credibility_tier="tier_1",
        enabled=True,
        collection_method="arxiv_api",
        extra_config={"categories": ["cs.AI", "cs.LG", "cs.CL"], "max_results": 40},
    )


def test_arxiv_parses_paper_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    xml = (FIXTURES / "arxiv_sample.xml").read_text(encoding="utf-8")
    monkeypatch.setattr(
        "app.collectors.arxiv_collector.fetch_url",
        lambda url, timeout=20: HttpResponse(url=url, status_code=200, text=xml, elapsed_ms=5),
    )
    items = ArxivCollector().collect(_source(), limit=40, timeout=20)
    assert len(items) == 2
    paper = items[0]
    assert paper.item_kind == ItemKind.RESEARCH_PAPER
    assert paper.url == "https://arxiv.org/abs/2608.01234"
    assert paper.extra["arxiv_id"] == "2608.01234"
    assert paper.author == "Grace Hopper, Alan Turing"
    assert "agentic RAG" in (paper.extra["abstract"] or "")
    assert "cs.AI" in paper.extra["categories"]
    assert paper.extra["pdf_url"].endswith(".pdf") or "pdf" in paper.extra["pdf_url"]
    assert items[1].url == "https://arxiv.org/abs/2608.05678"
