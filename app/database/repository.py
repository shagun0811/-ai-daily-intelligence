"""Small data-access helpers. Collectors and processors should use this layer."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.database.enums import ClusterMemberRole, FetchStatus, PipelineRunStatus, ProcessingStatus
from app.database.models import (
    Article,
    ArticleTopic,
    DailyReport,
    Embedding,
    ItemScore,
    LLMCache,
    PipelineRun,
    ProcessingResult,
    ResearchPaper,
    Source,
    SourceFetchLog,
    StoryCluster,
    StoryClusterMember,
    Topic,
)


class Repository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_source_by_name(self, name: str) -> Source | None:
        return self.session.scalar(select(Source).where(Source.name == name))

    def list_sources(self, *, enabled_only: bool = False) -> list[Source]:
        stmt = select(Source).order_by(Source.name)
        if enabled_only:
            stmt = stmt.where(Source.enabled.is_(True))
        return list(self.session.scalars(stmt).all())

    def get_article_by_url(self, url: str) -> Article | None:
        return self.session.scalar(select(Article).where(Article.url == url))

    def get_article_by_content_hash(self, content_hash: str) -> Article | None:
        return self.session.scalar(
            select(Article).where(Article.content_hash == content_hash)
        )

    def get_research_paper_by_arxiv_id(self, arxiv_id: str) -> ResearchPaper | None:
        return self.session.scalar(
            select(ResearchPaper).where(ResearchPaper.arxiv_id == arxiv_id)
        )

    def list_articles_by_status(self, statuses: list[str]) -> list[Article]:
        stmt = (
            select(Article)
            .options(
                selectinload(Article.source),
                selectinload(Article.research_paper),
                selectinload(Article.cluster_memberships)
                .selectinload(StoryClusterMember.cluster)
                .selectinload(StoryCluster.members),
                selectinload(Article.score),
                selectinload(Article.topic_links),
            )
            .where(Article.processing_status.in_(statuses))
            .order_by(Article.id)
        )
        return list(self.session.scalars(stmt).all())

    def create_article(
        self,
        *,
        source: Source,
        title: str,
        url: str,
        **fields: object,
    ) -> Article:
        article, _created = self.upsert_article(source=source, title=title, url=url, **fields)
        return article

    def upsert_article(
        self,
        *,
        source: Source,
        title: str,
        url: str,
        **fields: Any,
    ) -> tuple[Article, bool]:
        existing = self.get_article_by_url(url)
        if existing is not None:
            return existing, False
        article = Article(
            source_id=source.id,
            title=title,
            url=url,
            processing_status=ProcessingStatus.COLLECTED.value,
            **fields,
        )
        self.session.add(article)
        self.session.flush()
        return article, True

    def ensure_research_paper(
        self,
        article: Article,
        *,
        arxiv_id: str | None,
        abstract: str | None,
        authors_json: list[Any],
        categories_json: list[Any],
        pdf_url: str | None,
    ) -> ResearchPaper:
        if arxiv_id:
            existing = self.get_research_paper_by_arxiv_id(arxiv_id)
            if existing is not None:
                return existing
        paper = ResearchPaper(
            article_id=article.id,
            arxiv_id=arxiv_id,
            abstract=abstract,
            authors_json=authors_json,
            categories_json=categories_json,
            pdf_url=pdf_url,
        )
        self.session.add(paper)
        self.session.flush()
        return paper

    def create_pipeline_run(self, *, current_stage: str) -> PipelineRun:
        run = PipelineRun(
            status=PipelineRunStatus.RUNNING.value,
            current_stage=current_stage,
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(run)
        self.session.flush()
        return run

    def finish_pipeline_run(
        self,
        run: PipelineRun,
        *,
        status: PipelineRunStatus,
        successful_sources: int,
        failed_sources: int,
        articles_collected: int,
        research_papers_count: int,
        error_summary: str | None,
        current_stage: str | None = None,
        duplicates_removed: int = 0,
        relevant_articles: int = 0,
        average_importance: float | None = None,
        final_selected: int = 0,
    ) -> None:
        run.status = status.value
        run.successful_sources = successful_sources
        run.failed_sources = failed_sources
        run.articles_collected = articles_collected
        run.research_papers_count = research_papers_count
        run.duplicates_removed = duplicates_removed
        run.relevant_articles = relevant_articles
        run.final_selected = final_selected
        run.average_importance = average_importance
        run.error_summary = error_summary
        run.finished_at = datetime.now(timezone.utc)
        run.current_stage = current_stage or run.current_stage
        self.session.flush()

    def add_fetch_log(
        self,
        *,
        pipeline_run: PipelineRun,
        source: Source,
        status: FetchStatus,
        items_fetched: int,
        duration_ms: int | None = None,
        http_status: int | None = None,
        error: str | None = None,
    ) -> SourceFetchLog:
        log = SourceFetchLog(
            pipeline_run_id=pipeline_run.id,
            source_id=source.id,
            status=status.value,
            items_fetched=items_fetched,
            duration_ms=duration_ms,
            http_status=http_status,
            error=error,
        )
        self.session.add(log)
        self.session.flush()
        return log

    def upsert_embedding(
        self,
        article: Article,
        *,
        model_name: str,
        content_hash: str,
        dimension: int,
    ) -> Embedding:
        existing = self.session.scalar(
            select(Embedding).where(
                Embedding.article_id == article.id,
                Embedding.model_name == model_name,
                Embedding.content_hash == content_hash,
            )
        )
        if existing is not None:
            return existing
        row = Embedding(
            article_id=article.id,
            model_name=model_name,
            content_hash=content_hash,
            dimension=dimension,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def clear_story_clusters(self) -> None:
        self.session.execute(delete(StoryClusterMember))
        self.session.execute(delete(StoryCluster))
        self.session.flush()

    def create_story_cluster(
        self,
        *,
        event_title: str,
        primary_article: Article,
        cluster_date: datetime | None,
    ) -> StoryCluster:
        cluster = StoryCluster(
            event_title=event_title,
            primary_article_id=primary_article.id,
            cluster_date=cluster_date,
        )
        self.session.add(cluster)
        self.session.flush()
        return cluster

    def add_cluster_member(
        self,
        cluster: StoryCluster,
        article: Article,
        role: ClusterMemberRole,
    ) -> StoryClusterMember:
        existing = self.session.scalar(
            select(StoryClusterMember).where(
                StoryClusterMember.cluster_id == cluster.id,
                StoryClusterMember.article_id == article.id,
            )
        )
        if existing is not None:
            return existing
        member = StoryClusterMember(
            cluster_id=cluster.id,
            article_id=article.id,
            role=role.value,
        )
        self.session.add(member)
        self.session.flush()
        return member

    def get_processing_result(
        self,
        article: Article,
        *,
        stage: str,
        content_hash: str | None,
        model_used: str | None,
    ) -> ProcessingResult | None:
        stmt = (
            select(ProcessingResult)
            .where(
                ProcessingResult.article_id == article.id,
                ProcessingResult.stage == stage,
                ProcessingResult.content_hash == content_hash,
                ProcessingResult.model_used == model_used,
            )
            .order_by(ProcessingResult.id.desc())
        )
        return self.session.scalar(stmt)

    def get_llm_cache(self, prompt_hash: str, model: str) -> LLMCache | None:
        return self.session.scalar(
            select(LLMCache).where(LLMCache.prompt_hash == prompt_hash, LLMCache.model == model)
        )

    def upsert_llm_cache(
        self,
        *,
        prompt_hash: str,
        provider: str,
        model: str,
        response_json: dict[str, Any],
        response_text: str | None = None,
    ) -> LLMCache:
        existing = self.get_llm_cache(prompt_hash, model)
        if existing is not None:
            existing.provider = provider
            existing.response_json = response_json
            existing.response_text = response_text
            self.session.flush()
            return existing
        row = LLMCache(
            prompt_hash=prompt_hash,
            provider=provider,
            model=model,
            response_json=response_json,
            response_text=response_text,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def add_processing_result(
        self,
        article: Article,
        *,
        stage: str,
        model_used: str | None,
        content_hash: str | None,
        output_json: dict[str, Any],
    ) -> ProcessingResult:
        result = ProcessingResult(
            article_id=article.id,
            stage=stage,
            model_used=model_used,
            content_hash=content_hash,
            output_json=output_json,
        )
        self.session.add(result)
        self.session.flush()
        return result

    def get_topic_by_code(self, code: str) -> Topic | None:
        return self.session.scalar(select(Topic).where(Topic.code == code))

    def set_article_topics(self, article: Article, codes: list[str]) -> None:
        self.session.execute(delete(ArticleTopic).where(ArticleTopic.article_id == article.id))
        for code in codes:
            topic = self.get_topic_by_code(code)
            if topic is None:
                continue
            self.session.add(ArticleTopic(article_id=article.id, topic_id=topic.id))
        self.session.flush()

    def upsert_item_score(
        self,
        article: Article,
        *,
        recency: float,
        credibility: float,
        relevance: float,
        novelty: float,
        technical_significance: float,
        industry_impact: float,
        research_significance: float,
        weighted_total: float,
        explanation_json: dict[str, Any],
    ) -> ItemScore:
        existing = article.score
        if existing is None:
            existing = self.session.scalar(select(ItemScore).where(ItemScore.article_id == article.id))
        if existing is not None:
            existing.recency = recency
            existing.credibility = credibility
            existing.relevance = relevance
            existing.novelty = novelty
            existing.technical_significance = technical_significance
            existing.industry_impact = industry_impact
            existing.research_significance = research_significance
            existing.weighted_total = weighted_total
            existing.explanation_json = explanation_json
            self.session.flush()
            return existing
        row = ItemScore(
            article_id=article.id,
            recency=recency,
            credibility=credibility,
            relevance=relevance,
            novelty=novelty,
            technical_significance=technical_significance,
            industry_impact=industry_impact,
            research_significance=research_significance,
            weighted_total=weighted_total,
            explanation_json=explanation_json,
        )
        self.session.add(row)
        self.session.flush()
        article.score = row
        return row

    def upsert_daily_report(
        self,
        *,
        report_date,
        title: str,
        markdown_content: str,
        markdown_path: str,
        html_path: str,
        pdf_path: str,
        stats_json: dict[str, Any],
        pipeline_run_id: int | None,
    ) -> DailyReport:
        existing = self.session.scalar(select(DailyReport).where(DailyReport.report_date == report_date))
        if existing is not None:
            existing.title = title
            existing.markdown_content = markdown_content
            existing.markdown_path = markdown_path
            existing.html_path = html_path
            existing.pdf_path = pdf_path
            existing.stats_json = stats_json
            existing.pipeline_run_id = pipeline_run_id
            self.session.flush()
            return existing
        row = DailyReport(
            report_date=report_date,
            title=title,
            markdown_content=markdown_content,
            markdown_path=markdown_path,
            html_path=html_path,
            pdf_path=pdf_path,
            stats_json=stats_json,
            pipeline_run_id=pipeline_run_id,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def get_article_by_id(self, article_id: int) -> Article | None:
        stmt = (
            select(Article)
            .options(
                selectinload(Article.source),
                selectinload(Article.research_paper),
                selectinload(Article.score),
                selectinload(Article.topic_links).selectinload(ArticleTopic.topic),
                selectinload(Article.processing_results),
                selectinload(Article.cluster_memberships),
            )
            .where(Article.id == article_id)
        )
        return self.session.scalar(stmt)

    def list_daily_reports(self) -> list[DailyReport]:
        stmt = select(DailyReport).order_by(DailyReport.report_date.desc(), DailyReport.id.desc())
        return list(self.session.scalars(stmt).all())

    def previously_reported_article_ids(self, *, before_date: date) -> set[int]:
        """IDs already used in a report strictly before ``before_date``.

        Regenerating the same calendar date is allowed to reuse that day's items.
        Older reports without stored ``article_ids`` fall back to PUBLISHED rows.
        """
        used: set[int] = set()
        missing_ids = False
        for report in self.list_daily_reports():
            if report.report_date is None or report.report_date >= before_date:
                continue
            stored = (report.stats_json or {}).get("article_ids") or []
            if stored:
                for raw in stored:
                    try:
                        used.add(int(raw))
                    except (TypeError, ValueError):
                        continue
            else:
                missing_ids = True
        if missing_ids:
            published = self.list_articles_by_status([ProcessingStatus.PUBLISHED.value])
            used.update(article.id for article in published if article.id is not None)
        return used

    def count_articles(self) -> int:
        return int(self.session.scalar(select(func.count(Article.id))) or 0)
