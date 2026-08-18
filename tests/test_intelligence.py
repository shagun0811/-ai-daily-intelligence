"""Relevance, classification, and scoring tests. No LLM and no network."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.database.enums import (
    ClassificationCategory,
    ClusterMemberRole,
    ProcessingStatus,
    TopicCode,
)
from app.database.models import ArticleTopic, ItemScore
from app.database.repository import Repository
from app.processors.classifier import classify_article
from app.processors.intelligence import IntelligenceProcessor
from app.processors.relevance import score_relevance
from app.processors.scorer import recency_score, score_article
from app.processors.topics import extract_topics
from app.config.yaml_loader import load_scoring
from sqlalchemy import select


def _article(db_session, *, source_name: str, title: str, url: str, text: str, **fields):
    repo = Repository(db_session)
    source = repo.get_source_by_name(source_name)
    assert source is not None
    article = repo.create_article(
        source=source,
        title=title,
        url=url,
        cleaned_text=text,
        description=text,
        **fields,
    )
    article.processing_status = ProcessingStatus.DEDUPLICATED.value
    db_session.flush()
    db_session.refresh(article)
    return article


def test_research_paper_is_relevant_and_research(db_session) -> None:
    paper = _article(
        db_session,
        source_name="arXiv cs.AI / cs.LG / cs.CL",
        title="Efficient Retrieval for Agentic RAG Systems",
        url="https://arxiv.org/abs/2608.01234",
        text="We propose a retrieval method for agentic RAG.",
        item_kind="research_paper",
    )
    relevance = score_relevance(paper)
    assert relevance.relevant is True
    assert relevance.score >= 8.0
    classification = classify_article(paper)
    assert classification.category == ClassificationCategory.RESEARCH
    topics = extract_topics(paper)
    assert TopicCode.RAG in topics or TopicCode.AGENTS in topics


def test_model_release_beats_generic_company_news(db_session) -> None:
    article = _article(
        db_session,
        source_name="Google AI Blog",
        title="Google announces a new model release with open weights",
        url="https://blog.google/model-release",
        text="Weights available on Hugging Face. New model checkpoint.",
    )
    result = classify_article(article)
    assert result.category == ClassificationCategory.MODEL_RELEASE


def test_dinner_party_post_is_low_relevance(db_session) -> None:
    article = _article(
        db_session,
        source_name="Google AI Blog",
        title="5 ways to host the ultimate dinner party",
        url="https://blog.google/dinner-party",
        text="Seating chart tips and a cookie banner for the newsletter.",
    )
    relevance = score_relevance(article)
    assert relevance.relevant is False
    assert relevance.score < 4.0


def test_recency_decays_and_weights_are_from_config() -> None:
    scoring = load_scoring()
    assert abs(scoring.weights.total() - 1.0) < 1e-9

    class _Stamp:
        published_at = datetime.now(timezone.utc)
        collected_at = datetime.now(timezone.utc)

    fresh = recency_score(_Stamp(), scoring)  # type: ignore[arg-type]
    _Stamp.published_at = datetime.now(timezone.utc) - timedelta(days=10)
    old = recency_score(_Stamp(), scoring)  # type: ignore[arg-type]
    assert fresh == 10.0
    assert old < fresh


def test_supporting_source_has_lower_novelty(db_session) -> None:
    official = _article(
        db_session,
        source_name="Google AI Blog",
        title="Same event",
        url="https://blog.google/event-score",
        text="Official long announcement about a large language model.",
    )
    press = _article(
        db_session,
        source_name="TechCrunch AI",
        title="Same event",
        url="https://techcrunch.com/event-score",
        text="Short coverage of the large language model.",
    )
    repo = Repository(db_session)
    cluster = repo.create_story_cluster(
        event_title="Same event",
        primary_article=official,
        cluster_date=datetime.now(timezone.utc),
    )
    repo.add_cluster_member(cluster, official, ClusterMemberRole.PRIMARY)
    repo.add_cluster_member(cluster, press, ClusterMemberRole.SUPPORTING)
    db_session.refresh(official)
    db_session.refresh(press)
    official_score = score_article(official, category="MODEL_RELEASE")
    press_score = score_article(press, category="NEWS")
    assert official_score.novelty > press_score.novelty
    assert official_score.credibility > press_score.credibility
    assert official_score.weighted_total > press_score.weighted_total


def test_intelligence_processor_persists_scores_and_topics(db_session) -> None:
    paper = _article(
        db_session,
        source_name="arXiv cs.AI / cs.LG / cs.CL",
        title="A Small Language Model for On-Device Inference",
        url="https://arxiv.org/abs/2608.05678",
        text="A 1.5B parameter SLM evaluated on standard benchmarks.",
        item_kind="research_paper",
    )
    fluff = _article(
        db_session,
        source_name="Google AI Blog",
        title="Host a dinner party seating chart",
        url="https://blog.google/party",
        text="Cookie banner and newsletter seating chart.",
    )
    summary = IntelligenceProcessor(db_session).run()
    assert summary.classified == 2
    assert summary.scored == 2
    assert summary.relevant == 1
    db_session.refresh(paper)
    db_session.refresh(fluff)
    assert paper.processing_status == ProcessingStatus.SCORED.value
    assert paper.llm_category == ClassificationCategory.RESEARCH.value
    assert paper.score is not None
    assert fluff.score is not None
    assert paper.score.weighted_total > fluff.score.weighted_total
    links = list(db_session.scalars(select(ArticleTopic).where(ArticleTopic.article_id == paper.id)).all())
    assert links
    second = IntelligenceProcessor(db_session).run()
    assert second.skipped_already_scored == 2
    assert second.scored == 0
    scores = list(db_session.scalars(select(ItemScore)).all())
    assert len(scores) == 2
