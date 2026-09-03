"""Build the daily report from summarized items. Does not call an LLM."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config.logging import STAGE_RANK, STAGE_REPORT, STAGE_VALIDATE, get_logger, log_stage
from app.config.settings import get_settings
from app.config.yaml_loader import load_pipeline
from app.database.enums import PipelineRunStatus, ProcessingStatus
from app.database.models import Article, ArticleTopic, StoryCluster, StoryClusterMember
from app.database.repository import Repository
from app.media.builder import write_media_pack
from app.report.html import render_html
from app.report.markdown import render_markdown
from app.report.pdf import write_pdf
from app.report.ranker import build_document, is_supporting, latest_summary, mix_for_report, to_report_item
from app.utils.dates import today_ist
from app.report.validator import validate_item

logger = get_logger(__name__)


@dataclass
class ReportSummary:
    report_date: date | None = None
    candidates: int = 0
    selected: int = 0
    flagged: int = 0
    skipped_repeat: int = 0
    markdown_path: str | None = None
    html_path: str | None = None
    pdf_path: str | None = None
    infographic_path: str | None = None
    video_path: str | None = None
    mp4_path: str | None = None
    audio_path: str | None = None
    card_paths: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        lines = [
            f"Report date: {self.report_date}",
            f"Candidates: {self.candidates}",
            f"Selected for report: {self.selected}",
            f"Skipped already reported: {self.skipped_repeat}",
            f"Flagged claims: {self.flagged}",
            f"Markdown: {self.markdown_path}",
            f"HTML: {self.html_path}",
            f"PDF: {self.pdf_path}",
            f"Infographic: {self.infographic_path}",
            f"Story cards: {len(self.card_paths)}",
            f"Video: {self.video_path}",
            f"MP4: {self.mp4_path}",
            f"Audio: {self.audio_path}",
        ]
        if self.errors:
            lines.append("Errors:")
            lines.extend(f"  - {error}" for error in self.errors)
        return "\n".join(lines)


class ReportGenerator:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = Repository(session)
        self.settings = get_settings()

    def run(self, report_date: date | None = None, output_dir: Path | None = None) -> ReportSummary:
        report_date = report_date or self._today()
        summary = ReportSummary(report_date=report_date)
        run = self.repo.create_pipeline_run(current_stage=STAGE_VALIDATE)
        pipeline = load_pipeline()
        cap = min(self.settings.report_max_items, pipeline.report_max_items)

        articles = self._candidates()
        blocked = self._blocked_article_ids(report_date, articles)
        items = []
        for article in articles:
            if is_supporting(article):
                continue
            payload = latest_summary(article)
            if not payload:
                continue
            summary.candidates += 1
            validation = validate_item(article, payload)
            self.repo.add_processing_result(
                article,
                stage="VALIDATE",
                model_used="rules",
                content_hash=article.content_hash,
                output_json={"ok": validation.ok, "flags": validation.flags},
            )
            article.processing_status = ProcessingStatus.VALIDATED.value
            items.append(to_report_item(article, payload, validation))
            log_stage(
                logger,
                STAGE_VALIDATE,
                "article_id=%s ok=%s flags=%s",
                article.id,
                validation.ok,
                ",".join(validation.flags) or "-",
            )

        selected_pool = mix_for_report(
            items,
            cap=cap,
            blocked_ids=blocked,
            report_date=report_date,
        )
        selected_ids = {item.article_id for item in selected_pool}
        summary.skipped_repeat = sum(
            1 for item in items if item.article_id in blocked and item.article_id not in selected_ids
        )
        flagged = sum(1 for item in selected_pool if item.validation_flags)
        log_stage(
            logger,
            STAGE_RANK,
            "candidates=%s cap=%s selected=%s skipped_repeat=%s",
            len(items),
            cap,
            len(selected_pool),
            summary.skipped_repeat,
        )

        for article in articles:
            if article.id in selected_ids:
                article.processing_status = ProcessingStatus.PUBLISHED.value

        stats = {
            "candidates": summary.candidates,
            "selected": len(selected_pool),
            "flagged": flagged,
            "skipped_repeat": summary.skipped_repeat,
            "article_ids": [item.article_id for item in selected_pool],
        }
        document = build_document(selected_pool, report_date=report_date, stats=stats)
        out_dir = Path(output_dir) if output_dir is not None else self.settings.data_dir / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = f"ai-daily-intelligence-{report_date.isoformat()}"
        markdown_path = out_dir / f"{stem}.md"
        html_path = out_dir / f"{stem}.html"
        pdf_path = out_dir / f"{stem}.pdf"

        try:
            markdown_path.write_text(render_markdown(document), encoding="utf-8")
            html_path.write_text(render_html(document), encoding="utf-8")
            write_pdf(document, pdf_path)
        except Exception as exc:  # noqa: BLE001
            summary.errors.append(str(exc))
            log_stage(logger, STAGE_REPORT, "write failed error=%s", exc, level=40)
            self.repo.finish_pipeline_run(
                run,
                status=PipelineRunStatus.FAILED,
                current_stage=STAGE_REPORT,
                successful_sources=0,
                failed_sources=0,
                articles_collected=0,
                research_papers_count=0,
                final_selected=len(selected_pool),
                relevant_articles=summary.candidates,
                error_summary=str(exc),
            )
            return summary

        media = write_media_pack(document, out_dir=out_dir, stem=stem)
        summary.errors.extend(media.errors)
        stats.update(media.as_stats())

        self.repo.upsert_daily_report(
            report_date=report_date,
            title=document.title,
            markdown_content=markdown_path.read_text(encoding="utf-8"),
            markdown_path=str(markdown_path),
            html_path=str(html_path),
            pdf_path=str(pdf_path),
            stats_json=stats,
            pipeline_run_id=run.id,
        )
        self.session.flush()
        summary.selected = len(selected_pool)
        summary.flagged = flagged
        summary.markdown_path = str(markdown_path)
        summary.html_path = str(html_path)
        summary.pdf_path = str(pdf_path)
        summary.infographic_path = media.infographic_path
        summary.video_path = media.video_path
        summary.mp4_path = media.mp4_path
        summary.audio_path = media.audio_path
        summary.card_paths = list(media.card_paths)
        status = PipelineRunStatus.PARTIAL if summary.errors else PipelineRunStatus.SUCCESS
        self.repo.finish_pipeline_run(
            run,
            status=status,
            current_stage=STAGE_REPORT,
            successful_sources=0,
            failed_sources=0,
            articles_collected=0,
            research_papers_count=len(document.research),
            final_selected=summary.selected,
            relevant_articles=summary.candidates,
            error_summary="\n".join(summary.errors) if summary.errors else None,
        )
        log_stage(
            logger,
            STAGE_REPORT,
            "wrote md=%s html=%s pdf=%s infographic=%s gif=%s mp4=%s audio=%s selected=%s",
            markdown_path.name,
            html_path.name,
            pdf_path.name,
            Path(media.infographic_path).name if media.infographic_path else "-",
            Path(media.video_path).name if media.video_path else "-",
            Path(media.mp4_path).name if media.mp4_path else "-",
            Path(media.audio_path).name if media.audio_path else "-",
            summary.selected,
        )
        return summary

    def _blocked_article_ids(self, report_date: date, articles: list[Article]) -> set[int]:
        used = self.repo.previously_reported_article_ids(before_date=report_date)
        blocked = set(used)
        for article in articles:
            for membership in article.cluster_memberships:
                cluster = membership.cluster
                if cluster is None:
                    continue
                mate_ids = {
                    member.article_id for member in cluster.members if member.article_id is not None
                }
                if mate_ids & used:
                    blocked.update(mate_ids)
        return blocked

    def _today(self) -> date:
        return today_ist()

    def _candidates(self) -> list[Article]:
        stmt = (
            select(Article)
            .options(
                selectinload(Article.source),
                selectinload(Article.research_paper),
                selectinload(Article.score),
                selectinload(Article.topic_links).selectinload(ArticleTopic.topic),
                selectinload(Article.processing_results),
                selectinload(Article.cluster_memberships)
                .selectinload(StoryClusterMember.cluster)
                .selectinload(StoryCluster.members)
                .selectinload(StoryClusterMember.article)
                .selectinload(Article.source),
            )
            .where(
                Article.processing_status.in_(
                    [
                        ProcessingStatus.SUMMARIZED.value,
                        ProcessingStatus.VALIDATED.value,
                        ProcessingStatus.PUBLISHED.value,
                    ]
                )
            )
        )
        return list(self.session.scalars(stmt).unique().all())
