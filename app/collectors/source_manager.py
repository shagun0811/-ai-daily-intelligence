"""Run enabled sources. One failure never stops the rest."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic

from sqlalchemy.orm import Session

from app.collectors.arxiv_collector import ArxivCollector
from app.collectors.base import BaseCollector, CollectedItem, CollectorError
from app.collectors.rss_collector import RssCollector
from app.collectors.web_collector import WebCollector
from app.config.logging import STAGE_COLLECT, get_logger, log_stage
from app.config.settings import get_settings
from app.config.yaml_loader import load_pipeline
from app.database.enums import FetchStatus, ItemKind, PipelineRunStatus, SourceType
from app.database.models import PipelineRun, Source
from app.database.repository import Repository
from app.utils.hashing import content_hash
from app.utils.text import normalize_title, truncate

logger = get_logger(__name__)


@dataclass
class CollectionSummary:
    successful_sources: int = 0
    failed_sources: int = 0
    articles_collected: int = 0
    articles_skipped_existing: int = 0
    research_papers: int = 0
    errors: list[str] = field(default_factory=list)
    pipeline_run_id: int | None = None

    def as_text(self) -> str:
        lines = [
            f"Successful sources: {self.successful_sources}",
            f"Failed sources: {self.failed_sources}",
            f"New articles: {self.articles_collected}",
            f"Already stored (skipped): {self.articles_skipped_existing}",
            f"Research papers (new): {self.research_papers}",
        ]
        if self.errors:
            lines.append("Errors:")
            lines.extend(f"  - {error}" for error in self.errors)
        return "\n".join(lines)


class SourceManager:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = Repository(session)

    def run(self, *, enabled_only: bool = True) -> CollectionSummary:
        settings = get_settings()
        pipeline = load_pipeline()
        limit = settings.max_articles_per_source or pipeline.max_articles_per_source
        timeout = settings.http_timeout_seconds or pipeline.http_timeout_seconds

        run = self.repo.create_pipeline_run(current_stage=STAGE_COLLECT)
        summary = CollectionSummary(pipeline_run_id=run.id)
        sources = self.repo.list_sources(enabled_only=enabled_only)

        log_stage(logger, STAGE_COLLECT, "starting sources=%s limit=%s", len(sources), limit)

        for source in sources:
            started = monotonic()
            try:
                collector = collector_for(source)
                items = collector.collect(source, limit=limit, timeout=timeout)
            except CollectorError as exc:
                duration_ms = int((monotonic() - started) * 1000)
                self._record_failure(run, source, summary, str(exc), duration_ms)
                continue
            except Exception as exc:  # noqa: BLE001 — isolate unexpected source bugs
                duration_ms = int((monotonic() - started) * 1000)
                self._record_failure(
                    run,
                    source,
                    summary,
                    f"{type(exc).__name__}: {exc}",
                    duration_ms,
                )
                continue

            stored, skipped, papers = self._store_items(source, items)
            duration_ms = int((monotonic() - started) * 1000)
            self.repo.add_fetch_log(
                pipeline_run=run,
                source=source,
                status=FetchStatus.SUCCESS,
                items_fetched=stored,
                duration_ms=duration_ms,
            )
            summary.successful_sources += 1
            summary.articles_collected += stored
            summary.articles_skipped_existing += skipped
            summary.research_papers += papers
            log_stage(
                logger,
                STAGE_COLLECT,
                "ok source=%s stored=%s skipped=%s papers=%s duration_ms=%s",
                source.name,
                stored,
                skipped,
                papers,
                duration_ms,
            )

        if summary.failed_sources and summary.successful_sources:
            status = PipelineRunStatus.PARTIAL
        elif summary.failed_sources:
            status = PipelineRunStatus.FAILED
        else:
            status = PipelineRunStatus.SUCCESS

        self.repo.finish_pipeline_run(
            run,
            status=status,
            successful_sources=summary.successful_sources,
            failed_sources=summary.failed_sources,
            articles_collected=summary.articles_collected,
            research_papers_count=summary.research_papers,
            error_summary="\n".join(summary.errors) if summary.errors else None,
        )
        log_stage(
            logger,
            STAGE_COLLECT,
            "finished status=%s success=%s failed=%s stored=%s",
            status.value,
            summary.successful_sources,
            summary.failed_sources,
            summary.articles_collected,
        )
        return summary

    def _record_failure(
        self,
        run: PipelineRun,
        source: Source,
        summary: CollectionSummary,
        error: str,
        duration_ms: int,
    ) -> None:
        message = f"{source.name}: {error}"
        summary.failed_sources += 1
        summary.errors.append(message)
        self.repo.add_fetch_log(
            pipeline_run=run,
            source=source,
            status=FetchStatus.FAILED,
            items_fetched=0,
            duration_ms=duration_ms,
            error=truncate(error, 2000),
        )
        log_stage(logger, STAGE_COLLECT, "failed source=%s error=%s", source.name, error, level=40)

    def _store_items(self, source: Source, items: list[CollectedItem]) -> tuple[int, int, int]:
        stored = 0
        skipped = 0
        papers = 0
        for item in items:
            cleaned = item.cleaned_text or item.description or item.title
            article, created = self.repo.upsert_article(
                source=source,
                title=item.title,
                url=item.url,
                canonical_url=item.url,
                normalized_title=normalize_title(item.title),
                author=item.author,
                published_at=item.published_at,
                source_category=source.category,
                description=item.description,
                raw_text=item.raw_text,
                cleaned_text=cleaned,
                content_hash=content_hash(cleaned, item.url),
                item_kind=item.item_kind.value,
            )
            if not created:
                skipped += 1
                continue
            stored += 1
            if item.item_kind == ItemKind.RESEARCH_PAPER:
                extra = item.extra
                self.repo.ensure_research_paper(
                    article,
                    arxiv_id=extra.get("arxiv_id"),
                    abstract=extra.get("abstract") or cleaned,
                    authors_json=extra.get("authors") or [],
                    categories_json=extra.get("categories") or [],
                    pdf_url=extra.get("pdf_url"),
                )
                papers += 1
        return stored, skipped, papers


def collector_for(source: Source) -> BaseCollector:
    method = (source.collection_method or source.type or "").lower()
    source_type = source.type
    if method in {"rss", "atom"} or source_type == SourceType.RSS.value:
        return RssCollector()
    if method in {"arxiv", "arxiv_api"} or source_type == SourceType.ARXIV.value:
        return ArxivCollector()
    if method in {"webpage", "web"} or source_type == SourceType.WEBPAGE.value:
        return WebCollector()
    raise CollectorError(
        f"unsupported type={source.type} collection_method={source.collection_method}"
    )
