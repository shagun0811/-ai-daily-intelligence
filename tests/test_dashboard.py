"""Read-only dashboard query tests. Does not start Streamlit or hit the network."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from app.dashboard_data import dashboard_stats, filter_options, get_item_detail, list_reports, search_items
from app.dashboard_theme import CHART_COLORS, css_for
from app.database.enums import ProcessingStatus
from app.database.models import DailyReport
from app.database.repository import Repository
from app.utils.hashing import content_hash


def _article(db_session, *, source_name: str, title: str, url: str, text: str, **fields):
    repo = Repository(db_session)
    source = repo.get_source_by_name(source_name)
    assert source is not None
    status = fields.pop("processing_status", None)
    article = repo.create_article(
        source=source,
        title=title,
        url=url,
        cleaned_text=text,
        description=text,
        content_hash=content_hash(text, url),
        published_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
        **fields,
    )
    if status:
        article.processing_status = status
    db_session.flush()
    db_session.refresh(article)
    return article


def test_search_filters_and_stats(db_session) -> None:
    paper = _article(
        db_session,
        source_name="arXiv cs.AI / cs.LG / cs.CL",
        title="Agentic RAG retrieval paper",
        url="https://arxiv.org/abs/2608.77777",
        text="A retrieval-augmented generation method for agents.",
        item_kind="research_paper",
        llm_category="RESEARCH",
        processing_status=ProcessingStatus.PUBLISHED.value,
    )
    news = _article(
        db_session,
        source_name="Google AI Blog",
        title="Open weights large language model",
        url="https://blog.google/dash-news",
        text="Google released an open-weights large language model.",
        llm_category="MODEL_RELEASE",
        processing_status=ProcessingStatus.SCORED.value,
    )
    repo = Repository(db_session)
    repo.upsert_item_score(
        paper,
        recency=9,
        credibility=9,
        relevance=9,
        novelty=8,
        technical_significance=8,
        industry_impact=4,
        research_significance=9,
        weighted_total=8.4,
        explanation_json={"relevant": True},
    )
    repo.upsert_item_score(
        news,
        recency=8,
        credibility=8,
        relevance=7,
        novelty=7,
        technical_significance=6,
        industry_impact=8,
        research_significance=3,
        weighted_total=6.1,
        explanation_json={"relevant": True},
    )
    db_session.flush()

    options = filter_options(db_session)
    assert "Google AI Blog" in options["sources"]
    assert "RESEARCH" in options["categories"]

    stats = dashboard_stats(db_session)
    assert stats["articles"] >= 2
    assert stats["scored"] == 2
    assert stats["relevant"] == 2
    assert stats["average_score"] is not None

    found = search_items(db_session, query="agentic rag")
    assert any(item["id"] == paper.id for item in found)
    assert all("agentic" in item["title"].lower() or "rag" in item["title"].lower() for item in found)

    arxiv_only = search_items(db_session, source_name="arXiv cs.AI / cs.LG / cs.CL")
    assert {item["id"] for item in arxiv_only} == {paper.id}

    high = search_items(db_session, min_score=8.0)
    assert {item["id"] for item in high} == {paper.id}

    detail = get_item_detail(db_session, paper.id)
    assert detail is not None
    assert detail["url"] == paper.url
    assert detail["score_components"]["weighted_total"] == 8.4


def test_list_reports_and_missing_files(db_session, tmp_path: Path) -> None:
    md = tmp_path / "report.md"
    md.write_text("# hi", encoding="utf-8")
    row = DailyReport(
        report_date=date(2026, 8, 17),
        title="AI Daily Intelligence",
        markdown_content="# hi",
        markdown_path=str(md),
        html_path=str(tmp_path / "missing.html"),
        pdf_path=None,
        stats_json={"selected": 3, "candidates": 10},
    )
    db_session.add(row)
    db_session.flush()
    reports = list_reports(db_session)
    assert reports
    assert reports[0]["report_date"] == "2026-08-17"
    assert reports[0]["files"].get("markdown") == str(md)
    assert "html" not in reports[0]["files"]
    assert dashboard_stats(db_session)["reports"] >= 1


def test_light_and_dark_css_differ() -> None:
    dark = css_for("dark")
    light = css_for("light")
    assert "#0b1020" in dark
    assert "#f3efe4" in light
    assert "color: var(--text) !important" in dark
    assert "color: var(--text) !important" in light
    assert dark != light
    assert CHART_COLORS["light"]["status"] != CHART_COLORS["dark"]["status"]
