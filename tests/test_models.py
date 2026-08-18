"""Model and enum tests."""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.database.enums import (
    ClassificationCategory,
    ClusterMemberRole,
    ProcessingStatus,
    SourceType,
)
from app.database.models import DailyReport, ItemScore, PipelineRun, ResearchPaper, StoryCluster, StoryClusterMember
from app.database.repository import Repository


def test_processing_status_pipeline_order() -> None:
    expected = [
        "COLLECTED",
        "CLEANED",
        "DEDUPLICATED",
        "CLASSIFIED",
        "SCORED",
        "SUMMARIZED",
        "VALIDATED",
        "PUBLISHED",
        "FAILED",
    ]
    assert [status.value for status in ProcessingStatus] == expected


def test_classification_categories_are_structured() -> None:
    assert ClassificationCategory.MODEL_RELEASE.value == "MODEL_RELEASE"
    assert ClassificationCategory.RESEARCH.value == "RESEARCH"
    assert SourceType.ARXIV.value == "arxiv"


def test_research_paper_extends_article(db_session) -> None:
    repo = Repository(db_session)
    source = repo.get_source_by_name("arXiv cs.AI / cs.LG / cs.CL")
    assert source is not None
    article = repo.create_article(
        source=source,
        title="A mocked paper",
        url="https://arxiv.org/abs/0000.00001",
        item_kind="research_paper",
    )
    paper = ResearchPaper(
        article_id=article.id,
        arxiv_id="0000.00001",
        abstract="Mock abstract.",
        authors_json=["Ada Lovelace"],
        categories_json=["cs.AI"],
    )
    db_session.add(paper)
    db_session.flush()
    db_session.refresh(article)
    assert article.research_paper is not None
    assert article.research_paper.arxiv_id == "0000.00001"


def test_story_cluster_keeps_supporting_sources(db_session) -> None:
    repo = Repository(db_session)
    primary_source = repo.get_source_by_name("Google AI Blog")
    support_source = repo.get_source_by_name("TechCrunch AI")
    assert primary_source and support_source
    primary = repo.create_article(
        source=primary_source,
        title="Official model announcement",
        url="https://blog.google/example-model",
    )
    supporting = repo.create_article(
        source=support_source,
        title="Coverage of the model announcement",
        url="https://techcrunch.com/example-model",
    )
    cluster = StoryCluster(event_title="New AI model released", primary_article_id=primary.id)
    db_session.add(cluster)
    db_session.flush()
    db_session.add_all(
        [
            StoryClusterMember(
                cluster_id=cluster.id,
                article_id=primary.id,
                role=ClusterMemberRole.PRIMARY.value,
            ),
            StoryClusterMember(
                cluster_id=cluster.id,
                article_id=supporting.id,
                role=ClusterMemberRole.SUPPORTING.value,
            ),
        ]
    )
    db_session.flush()
    assert len(cluster.members) == 2
    roles = {member.role for member in cluster.members}
    assert roles == {"primary", "supporting"}


def test_item_score_components_are_stored(db_session) -> None:
    repo = Repository(db_session)
    source = repo.list_sources()[0]
    article = repo.create_article(source=source, title="Scored", url="https://example.com/scored")
    score = ItemScore(
        article_id=article.id,
        recency=8.0,
        credibility=7.0,
        relevance=9.0,
        novelty=6.0,
        technical_significance=8.0,
        industry_impact=5.0,
        research_significance=4.0,
        weighted_total=6.95,
        explanation_json={"note": "mock"},
    )
    db_session.add(score)
    db_session.flush()
    assert article.score is not None
    assert article.score.weighted_total == 6.95


def test_daily_report_and_pipeline_run(db_session) -> None:
    run = PipelineRun(successful_sources=3, failed_sources=2, articles_collected=0)
    db_session.add(run)
    db_session.flush()
    report = DailyReport(
        report_date=date(2026, 8, 16),
        title="AI Daily Intelligence",
        markdown_content="# Mock",
        pipeline_run_id=run.id,
        stats_json={"articles_collected": 0},
    )
    db_session.add(report)
    db_session.flush()
    assert report.pipeline_run_id == run.id
    assert run.started_at.tzinfo is not None or isinstance(run.started_at, datetime)
    _ = timezone.utc
