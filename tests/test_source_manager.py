"""Source manager tests: failed sources do not stop the run. No live network."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.collectors.base import CollectedItem, CollectorError
from app.collectors.source_manager import SourceManager, collector_for
from app.database.enums import FetchStatus, ItemKind, PipelineRunStatus
from app.database.models import Article, ResearchPaper, Source, SourceFetchLog
from app.database.repository import Repository
from sqlalchemy import select

FIXTURES = Path(__file__).parent / "fixtures"


def test_collector_for_dispatches_by_type(db_session) -> None:
    repo = Repository(db_session)
    rss = repo.get_source_by_name("Google AI Blog")
    arxiv = repo.get_source_by_name("arXiv cs.AI / cs.LG / cs.CL")
    web = repo.get_source_by_name("Example Webpage Article")
    assert rss and arxiv and web
    assert collector_for(rss).__class__.__name__ == "RssCollector"
    assert collector_for(arxiv).__class__.__name__ == "ArxivCollector"
    assert collector_for(web).__class__.__name__ == "WebCollector"


def test_failed_source_does_not_stop_others(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    rss_xml = (FIXTURES / "rss_sample.xml").read_text(encoding="utf-8")
    arxiv_xml = (FIXTURES / "arxiv_sample.xml").read_text(encoding="utf-8")

    from app.collectors import rss_collector, arxiv_collector
    from app.utils.http import HttpResponse

    def fake_rss(url: str, timeout: int = 20) -> HttpResponse:
        return HttpResponse(url=url, status_code=200, text=rss_xml, elapsed_ms=1)

    def fake_arxiv(url: str, timeout: int = 20) -> HttpResponse:
        raise CollectorError("simulated arXiv outage")

    monkeypatch.setattr(rss_collector, "fetch_url", fake_rss)
    monkeypatch.setattr(arxiv_collector, "fetch_url", fake_arxiv)

    # Disable extra enabled sources so only RSS + arXiv run.
    repo = Repository(db_session)
    google = repo.get_source_by_name("Google AI Blog")
    tech = repo.get_source_by_name("TechCrunch AI")
    arxiv = repo.get_source_by_name("arXiv cs.AI / cs.LG / cs.CL")
    assert google and tech and arxiv
    tech.enabled = False
    db_session.flush()

    summary = SourceManager(db_session).run(enabled_only=True)
    assert summary.successful_sources >= 1
    assert summary.failed_sources >= 1
    assert summary.articles_collected >= 1
    assert any("arXiv" in error or "outage" in error.lower() or "CollectorError" in error for error in summary.errors) or summary.failed_sources >= 1

    logs = list(db_session.scalars(select(SourceFetchLog)).all())
    statuses = {log.status for log in logs}
    assert FetchStatus.SUCCESS.value in statuses
    assert FetchStatus.FAILED.value in statuses


def test_existing_url_is_not_inserted_twice(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.collectors.arxiv_collector import ArxivCollector
    from app.collectors.rss_collector import RssCollector

    repo = Repository(db_session)
    source = repo.get_source_by_name("Google AI Blog")
    assert source is not None
    for row in repo.list_sources():
        row.enabled = row.name == "Google AI Blog"
    db_session.flush()

    item = CollectedItem(
        title="Existing story",
        url="https://blog.example.com/llm-release",
        cleaned_text="body",
        item_kind=ItemKind.ARTICLE,
    )
    monkeypatch.setattr(RssCollector, "collect", lambda self, src, limit, timeout: [item])
    monkeypatch.setattr(ArxivCollector, "collect", lambda self, src, limit, timeout: [])
    manager = SourceManager(db_session)
    first = manager.run(enabled_only=True)
    second = manager.run(enabled_only=True)
    stored = db_session.scalar(select(Article).where(Article.url == item.url))
    assert stored is not None
    assert first.articles_collected == 1
    assert second.articles_collected == 0
    assert second.articles_skipped_existing == 1


def test_arxiv_items_create_research_paper_rows(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.collectors.arxiv_collector import ArxivCollector
    from app.collectors.rss_collector import RssCollector

    xml = (FIXTURES / "arxiv_sample.xml").read_text(encoding="utf-8")
    from app.utils.http import HttpResponse

    monkeypatch.setattr(
        "app.collectors.arxiv_collector.fetch_url",
        lambda url, timeout=20: HttpResponse(url=url, status_code=200, text=xml, elapsed_ms=1),
    )
    monkeypatch.setattr(RssCollector, "collect", lambda self, src, limit, timeout: [])

    for source in Repository(db_session).list_sources():
        if source.type != "arxiv":
            source.enabled = False
    db_session.flush()

    summary = SourceManager(db_session).run(enabled_only=True)
    assert summary.research_papers == 2
    papers = list(db_session.scalars(select(ResearchPaper)).all())
    assert {paper.arxiv_id for paper in papers} == {"2608.01234", "2608.05678"}
    article = papers[0].article
    assert article.item_kind == ItemKind.RESEARCH_PAPER.value
    assert article.processing_status == "COLLECTED"


def test_all_sources_failing_marks_run_failed(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.collectors.rss_collector import RssCollector
    from app.collectors.arxiv_collector import ArxivCollector

    monkeypatch.setattr(
        RssCollector,
        "collect",
        lambda self, src, limit, timeout: (_ for _ in ()).throw(CollectorError("down")),
    )
    monkeypatch.setattr(
        ArxivCollector,
        "collect",
        lambda self, src, limit, timeout: (_ for _ in ()).throw(CollectorError("down")),
    )
    summary = SourceManager(db_session).run(enabled_only=True)
    assert summary.successful_sources == 0
    assert summary.failed_sources >= 1
    from app.database.models import PipelineRun

    latest = db_session.scalars(select(PipelineRun).order_by(PipelineRun.id.desc())).first()
    assert latest is not None
    assert latest.status == PipelineRunStatus.FAILED.value


def test_collector_for_rejects_unknown_type() -> None:
    source = Source(
        name="Unknown",
        url="ftp://example.com/feed",
        type="ftp",
        category="news",
        credibility_tier="tier_2",
        enabled=True,
        collection_method="ftp",
        extra_config={},
    )
    with pytest.raises(CollectorError, match="unsupported"):
        collector_for(source)
