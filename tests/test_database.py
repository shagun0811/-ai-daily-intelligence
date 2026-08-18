"""Database bootstrap and repository tests. No live websites."""

from __future__ import annotations

from app.database.enums import ProcessingStatus, TopicCode
from app.database.models import Article, Source, Topic
from app.database.repository import Repository
from app.utils.hashing import content_hash, sha256_text
from sqlalchemy import inspect, select, text

from app.database.database import get_engine


def test_schema_creates_expected_tables(isolated_db) -> None:
    inspector = inspect(get_engine())
    tables = set(inspector.get_table_names())
    expected = {
        "sources",
        "articles",
        "research_papers",
        "topics",
        "tags",
        "article_topics",
        "article_tags",
        "story_clusters",
        "story_cluster_members",
        "processing_results",
        "item_scores",
        "embeddings",
        "llm_cache",
        "daily_reports",
        "pipeline_runs",
        "source_fetch_logs",
    }
    assert expected.issubset(tables)


def test_sources_and_topics_are_seeded(db_session) -> None:
    sources = list(db_session.scalars(select(Source)).all())
    topics = list(db_session.scalars(select(Topic)).all())
    assert len(sources) >= 5
    assert {topic.code for topic in topics} == {code.value for code in TopicCode}
    enabled = [row for row in sources if row.enabled]
    assert any(row.name == "Google AI Blog" for row in enabled)


def test_repository_inserts_article_once(db_session) -> None:
    repo = Repository(db_session)
    source = repo.get_source_by_name("Google AI Blog")
    assert source is not None
    first = repo.create_article(
        source=source,
        title="Example model release",
        url="https://example.com/ai/model",
        description="A mocked article.",
        content_hash=content_hash("body", "https://example.com/ai/model"),
    )
    second = repo.create_article(
        source=source,
        title="Example model release",
        url="https://example.com/ai/model",
    )
    assert first.id == second.id
    assert first.processing_status == ProcessingStatus.COLLECTED.value
    assert repo.count_articles() == 1


def test_article_url_is_unique(db_session) -> None:
    repo = Repository(db_session)
    source = repo.list_sources(enabled_only=True)[0]
    repo.create_article(source=source, title="A", url="https://example.com/unique")
    db_session.flush()
    duplicate = db_session.scalar(select(Article).where(Article.url == "https://example.com/unique"))
    assert duplicate is not None


def test_content_hash_is_stable() -> None:
    assert sha256_text("abc") == sha256_text("abc")
    assert content_hash("text", "https://a") != content_hash("text", "https://b")
    assert content_hash("text", "https://a") != content_hash("other", "https://a")


def test_sqlite_uses_wal_and_busy_timeout(isolated_db) -> None:
    with get_engine().connect() as connection:
        mode = connection.execute(text("PRAGMA journal_mode")).scalar()
        timeout = connection.execute(text("PRAGMA busy_timeout")).scalar()
    assert str(mode).lower() == "wal"
    assert int(timeout) >= 5000
