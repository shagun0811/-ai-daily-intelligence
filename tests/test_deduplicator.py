"""Duplicate detection and story grouping. Uses mock embeddings — no model download."""

from __future__ import annotations

import numpy as np

from app.database.enums import ClusterMemberRole, ProcessingStatus
from app.database.models import StoryCluster, StoryClusterMember
from app.database.repository import Repository
from app.processors.deduplicator import (
    choose_primary,
    cluster_articles,
    find_duplicate_pairs,
    title_similarity,
)
from app.processors.embedder import HashEmbedder, cosine_similarity_matrix
from app.processors.pipeline import ContentProcessor
from sqlalchemy import select


def _article(db_session, *, source_name: str, title: str, url: str, text: str, **fields):
    repo = Repository(db_session)
    source = repo.get_source_by_name(source_name)
    assert source is not None
    return repo.create_article(
        source=source,
        title=title,
        url=url,
        cleaned_text=text,
        description=text,
        **fields,
    )


def test_title_similarity_and_hash_embeddings() -> None:
    assert title_similarity("openai releases gpt 5", "openai releases gpt 5") == 1.0
    assert title_similarity("openai releases gpt 5", "stock market closes mixed") < 0.5
    vectors = HashEmbedder().encode(["alpha beta gamma", "alpha beta gamma", "unrelated zebra"])
    matrix = cosine_similarity_matrix(vectors)
    assert matrix[0, 1] > 0.99
    assert matrix[0, 2] < 0.6


def test_canonical_url_and_title_duplicates_are_grouped(db_session) -> None:
    official = _article(
        db_session,
        source_name="Google AI Blog",
        title="Official model announcement",
        url="https://blog.google/model?utm_source=twitter",
        text="Google released a model.",
        canonical_url="https://blog.google/model",
        normalized_title="official model announcement",
    )
    coverage = _article(
        db_session,
        source_name="TechCrunch AI",
        title="Official model announcement | TechCrunch",
        url="https://techcrunch.com/model-coverage",
        text="TechCrunch covers the Google model.",
        canonical_url="https://techcrunch.com/model-coverage",
        normalized_title="official model announcement",
    )
    unrelated = _article(
        db_session,
        source_name="TechCrunch AI",
        title="Unrelated funding round",
        url="https://techcrunch.com/funding",
        text="A startup raised money.",
        canonical_url="https://techcrunch.com/funding",
        normalized_title="unrelated funding round",
    )
    db_session.flush()
    pairs = find_duplicate_pairs(
        [official, coverage, unrelated],
        vectors=None,
        title_threshold=0.92,
        semantic_threshold=0.88,
    )
    reasons = {pair.reason for pair in pairs}
    assert "normalized_title" in reasons
    groups = cluster_articles([official, coverage, unrelated], pairs)
    clustered = [group for group in groups if len(group) > 1]
    assert len(clustered) == 1
    member_ids = {article.id for article in clustered[0]}
    assert member_ids == {official.id, coverage.id}


def test_semantic_duplicates_with_injected_vectors(db_session) -> None:
    left = _article(
        db_session,
        source_name="Google AI Blog",
        title="Alpha research update",
        url="https://blog.google/alpha",
        text="alpha",
        normalized_title="alpha research update",
    )
    right = _article(
        db_session,
        source_name="TechCrunch AI",
        title="Completely different headline",
        url="https://techcrunch.com/beta",
        text="beta",
        normalized_title="completely different headline",
    )
    db_session.flush()
    vectors = np.array([[1.0, 0.0], [0.99, 0.141]], dtype=np.float32)
    pairs = find_duplicate_pairs(
        [left, right],
        vectors=vectors,
        title_threshold=1.01,
        semantic_threshold=0.88,
    )
    assert len(pairs) == 1
    assert pairs[0].reason == "semantic"


def test_primary_prefers_tier_one_but_keeps_supporting(db_session) -> None:
    official = _article(
        db_session,
        source_name="Google AI Blog",
        title="Same event",
        url="https://blog.google/event",
        text="Official long writeup " * 20,
        normalized_title="same event",
    )
    press = _article(
        db_session,
        source_name="TechCrunch AI",
        title="Same event",
        url="https://techcrunch.com/event",
        text="Short coverage",
        normalized_title="same event",
    )
    db_session.flush()
    db_session.refresh(official)
    db_session.refresh(press)
    primary = choose_primary([press, official])
    assert primary.id == official.id


def test_content_processor_groups_without_deleting(db_session, monkeypatch) -> None:
    monkeypatch.setenv("EXTRACT_FULL_TEXT", "false")
    from app.config.settings import clear_settings_cache

    clear_settings_cache()
    official = _article(
        db_session,
        source_name="Google AI Blog",
        title="New Gemini model released",
        url="https://blog.google/gemini",
        text="Google announced Gemini.",
    )
    press = _article(
        db_session,
        source_name="TechCrunch AI",
        title="New Gemini model released",
        url="https://techcrunch.com/gemini",
        text="TechCrunch reports Gemini.",
    )
    db_session.flush()
    summary = ContentProcessor(db_session).run()
    assert summary.cleaned == 2
    assert summary.clusters == 1
    assert summary.grouped_as_supporting == 1
    db_session.refresh(official)
    db_session.refresh(press)
    assert official.processing_status == ProcessingStatus.DEDUPLICATED.value
    assert press.processing_status == ProcessingStatus.DEDUPLICATED.value
    members = list(db_session.scalars(select(StoryClusterMember)).all())
    assert len(members) == 2
    roles = {member.role for member in members}
    assert roles == {ClusterMemberRole.PRIMARY.value, ClusterMemberRole.SUPPORTING.value}
    clusters = list(db_session.scalars(select(StoryCluster)).all())
    assert len(clusters) == 1

    again = ContentProcessor(db_session).run()
    assert again.cleaned == 0
    assert again.skipped_recluster >= 2
    assert again.clusters == 0
    still = list(db_session.scalars(select(StoryCluster)).all())
    assert len(still) == 1


def test_failed_extraction_does_not_stop_processing(db_session, monkeypatch) -> None:
    monkeypatch.setenv("EXTRACT_FULL_TEXT", "true")
    monkeypatch.setenv("MIN_CLEANED_TEXT_CHARS", "10")
    monkeypatch.setenv("MAX_FULL_TEXT_EXTRACTS", "5")
    from app.config.settings import clear_settings_cache

    clear_settings_cache()
    _article(
        db_session,
        source_name="TechCrunch AI",
        title="Short snippet story",
        url="https://techcrunch.com/snippet",
        text="tiny",
    )
    monkeypatch.setattr(
        "app.processors.pipeline.extract_full_text",
        lambda url, timeout=20, html=None: None,
    )
    summary = ContentProcessor(db_session).run()
    assert summary.extract_failed == 1
    assert summary.cleaned == 1
    assert not summary.errors
