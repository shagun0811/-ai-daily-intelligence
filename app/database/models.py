"""SQLAlchemy models. Provenance is preserved; duplicates are clustered, not deleted."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base
from app.database.enums import (
    ClusterMemberRole,
    CredibilityTier,
    FetchStatus,
    ItemKind,
    PipelineRunStatus,
    ProcessingStatus,
    SourceType,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )


class Source(TimestampMixin, Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    type: Mapped[str] = mapped_column(String(32), default=SourceType.RSS.value, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    credibility_tier: Mapped[str] = mapped_column(
        String(16),
        default=CredibilityTier.TIER_2.value,
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    collection_method: Mapped[str] = mapped_column(String(64), nullable=False)
    extra_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    articles: Mapped[list[Article]] = relationship(back_populates="source")
    fetch_logs: Mapped[list[SourceFetchLog]] = relationship(back_populates="source")


class Article(TimestampMixin, Base):
    __tablename__ = "articles"
    __table_args__ = (UniqueConstraint("url", name="uq_articles_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    normalized_title: Mapped[str | None] = mapped_column(String(1024), index=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(2048), index=True)
    author: Mapped[str | None] = mapped_column(String(512))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    source_category: Mapped[str | None] = mapped_column(String(64))
    llm_category: Mapped[str | None] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)
    cleaned_text: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    processing_status: Mapped[str] = mapped_column(
        String(32),
        default=ProcessingStatus.COLLECTED.value,
        nullable=False,
        index=True,
    )
    processing_error: Mapped[str | None] = mapped_column(Text)
    item_kind: Mapped[str] = mapped_column(
        String(32),
        default=ItemKind.ARTICLE.value,
        nullable=False,
    )
    classification_confidence: Mapped[float | None] = mapped_column(Float)

    source: Mapped[Source] = relationship(back_populates="articles")
    research_paper: Mapped[Optional[ResearchPaper]] = relationship(
        back_populates="article",
        uselist=False,
        cascade="all, delete-orphan",
    )
    processing_results: Mapped[list[ProcessingResult]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
    )
    score: Mapped[Optional[ItemScore]] = relationship(
        back_populates="article",
        uselist=False,
        cascade="all, delete-orphan",
    )
    embeddings: Mapped[list[Embedding]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
    )
    topic_links: Mapped[list[ArticleTopic]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
    )
    tag_links: Mapped[list[ArticleTag]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
    )
    cluster_memberships: Mapped[list[StoryClusterMember]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
    )


class ResearchPaper(TimestampMixin, Base):
    __tablename__ = "research_papers"
    __table_args__ = (UniqueConstraint("arxiv_id", name="uq_research_papers_arxiv_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id"),
        unique=True,
        nullable=False,
    )
    arxiv_id: Mapped[str | None] = mapped_column(String(64), index=True)
    abstract: Mapped[str | None] = mapped_column(Text)
    authors_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    categories_json: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    pdf_url: Mapped[str | None] = mapped_column(String(2048))
    key_contribution: Mapped[str | None] = mapped_column(Text)
    methodology: Mapped[str | None] = mapped_column(Text)
    results: Mapped[str | None] = mapped_column(Text)
    limitations: Mapped[str | None] = mapped_column(Text)
    research_significance: Mapped[str | None] = mapped_column(Text)

    article: Mapped[Article] = relationship(back_populates="research_paper")


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    article_links: Mapped[list[ArticleTopic]] = relationship(back_populates="topic")


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    article_links: Mapped[list[ArticleTag]] = relationship(back_populates="tag")


class ArticleTopic(Base):
    __tablename__ = "article_topics"
    __table_args__ = (UniqueConstraint("article_id", "topic_id", name="uq_article_topic"),)

    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), primary_key=True)

    article: Mapped[Article] = relationship(back_populates="topic_links")
    topic: Mapped[Topic] = relationship(back_populates="article_links")


class ArticleTag(Base):
    __tablename__ = "article_tags"
    __table_args__ = (UniqueConstraint("article_id", "tag_id", name="uq_article_tag"),)

    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id"), primary_key=True)

    article: Mapped[Article] = relationship(back_populates="tag_links")
    tag: Mapped[Tag] = relationship(back_populates="article_links")


class StoryCluster(TimestampMixin, Base):
    __tablename__ = "story_clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_title: Mapped[str] = mapped_column(String(1024), nullable=False)
    cluster_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    primary_article_id: Mapped[int | None] = mapped_column(ForeignKey("articles.id"))

    members: Mapped[list[StoryClusterMember]] = relationship(
        back_populates="cluster",
        cascade="all, delete-orphan",
    )
    primary_article: Mapped[Optional[Article]] = relationship(foreign_keys=[primary_article_id])


class StoryClusterMember(Base):
    __tablename__ = "story_cluster_members"
    __table_args__ = (UniqueConstraint("cluster_id", "article_id", name="uq_cluster_article"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("story_clusters.id"), nullable=False)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False)
    role: Mapped[str] = mapped_column(
        String(16),
        default=ClusterMemberRole.SUPPORTING.value,
        nullable=False,
    )

    cluster: Mapped[StoryCluster] = relationship(back_populates="members")
    article: Mapped[Article] = relationship(back_populates="cluster_memberships")


class ProcessingResult(TimestampMixin, Base):
    __tablename__ = "processing_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    model_used: Mapped[str | None] = mapped_column(String(128))
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    output_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)

    article: Mapped[Article] = relationship(back_populates="processing_results")


class ItemScore(TimestampMixin, Base):
    __tablename__ = "item_scores"
    __table_args__ = (UniqueConstraint("article_id", name="uq_item_scores_article"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False)
    recency: Mapped[float] = mapped_column(Float, nullable=False)
    credibility: Mapped[float] = mapped_column(Float, nullable=False)
    relevance: Mapped[float] = mapped_column(Float, nullable=False)
    novelty: Mapped[float] = mapped_column(Float, nullable=False)
    technical_significance: Mapped[float] = mapped_column(Float, nullable=False)
    industry_impact: Mapped[float] = mapped_column(Float, nullable=False)
    research_significance: Mapped[float] = mapped_column(Float, nullable=False)
    weighted_total: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    explanation_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    article: Mapped[Article] = relationship(back_populates="score")


class Embedding(TimestampMixin, Base):
    __tablename__ = "embeddings"
    __table_args__ = (
        UniqueConstraint("article_id", "model_name", "content_hash", name="uq_embedding_article_model_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    faiss_id: Mapped[int | None] = mapped_column(Integer)
    dimension: Mapped[int | None] = mapped_column(Integer)

    article: Mapped[Article] = relationship(back_populates="embeddings")


class LLMCache(TimestampMixin, Base):
    __tablename__ = "llm_cache"
    __table_args__ = (UniqueConstraint("prompt_hash", "model", name="uq_llm_cache_prompt_model"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    response_text: Mapped[str | None] = mapped_column(Text)
    response_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class DailyReport(TimestampMixin, Base):
    __tablename__ = "daily_reports"
    __table_args__ = (UniqueConstraint("report_date", name="uq_daily_reports_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    markdown_content: Mapped[str | None] = mapped_column(Text)
    markdown_path: Mapped[str | None] = mapped_column(String(1024))
    html_path: Mapped[str | None] = mapped_column(String(1024))
    pdf_path: Mapped[str | None] = mapped_column(String(1024))
    stats_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    pipeline_run_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_runs.id"))

    pipeline_run: Mapped[Optional[PipelineRun]] = relationship(back_populates="reports")


class PipelineRun(TimestampMixin, Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(16),
        default=PipelineRunStatus.RUNNING.value,
        nullable=False,
        index=True,
    )
    current_stage: Mapped[str | None] = mapped_column(String(32))
    successful_sources: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_sources: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    articles_collected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicates_removed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    relevant_articles: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    research_papers_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    final_selected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_importance: Mapped[float | None] = mapped_column(Float)
    error_summary: Mapped[str | None] = mapped_column(Text)

    fetch_logs: Mapped[list[SourceFetchLog]] = relationship(
        back_populates="pipeline_run",
        cascade="all, delete-orphan",
    )
    reports: Mapped[list[DailyReport]] = relationship(back_populates="pipeline_run")


class SourceFetchLog(TimestampMixin, Base):
    __tablename__ = "source_fetch_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False, index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default=FetchStatus.SUCCESS.value, nullable=False)
    items_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)

    pipeline_run: Mapped[PipelineRun] = relationship(back_populates="fetch_logs")
    source: Mapped[Source] = relationship(back_populates="fetch_logs")
