"""Phase 4: relevance, classify, topics, and importance scores. No LLM."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.config.logging import STAGE_CLASSIFY, STAGE_FILTER, STAGE_SCORE, get_logger, log_stage
from app.config.taxonomy import load_taxonomy
from app.config.yaml_loader import load_scoring
from app.database.enums import PipelineRunStatus, ProcessingStatus
from app.database.repository import Repository
from app.processors.classifier import classify_article
from app.processors.relevance import score_relevance
from app.processors.scorer import score_article
from app.processors.topics import extract_topics

logger = get_logger(__name__)


@dataclass
class IntelligenceSummary:
    classified: int = 0
    scored: int = 0
    relevant: int = 0
    skipped_already_scored: int = 0
    average_score: float = 0.0
    errors: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        lines = [
            f"Classified: {self.classified}",
            f"Scored: {self.scored}",
            f"Relevant: {self.relevant}",
            f"Already scored (skipped): {self.skipped_already_scored}",
            f"Average importance: {self.average_score:.2f}",
        ]
        if self.errors:
            lines.append("Errors:")
            lines.extend(f"  - {error}" for error in self.errors)
        return "\n".join(lines)


class IntelligenceProcessor:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = Repository(session)

    def run(self) -> IntelligenceSummary:
        taxonomy = load_taxonomy()
        scoring = load_scoring()
        summary = IntelligenceSummary()
        run = self.repo.create_pipeline_run(current_stage=STAGE_FILTER)

        pending = self.repo.list_articles_by_status(
            [ProcessingStatus.DEDUPLICATED.value, ProcessingStatus.CLASSIFIED.value]
        )
        already_scored = self.repo.list_articles_by_status([ProcessingStatus.SCORED.value])
        summary.skipped_already_scored = len(already_scored)
        log_stage(logger, STAGE_FILTER, "pending=%s already_scored=%s", len(pending), len(already_scored))

        totals: list[float] = []
        for article in pending:
            try:
                relevance = score_relevance(article, taxonomy)
                classification = classify_article(article, taxonomy)
                topics = extract_topics(article, taxonomy)
                article.llm_category = classification.category.value
                article.classification_confidence = classification.confidence
                article.processing_status = ProcessingStatus.CLASSIFIED.value
                self.repo.set_article_topics(article, [topic.value for topic in topics])
                self.repo.add_processing_result(
                    article,
                    stage="CLASSIFY",
                    model_used="rules",
                    content_hash=article.content_hash,
                    output_json=classification.model_dump(),
                )
                summary.classified += 1
                if relevance.relevant:
                    summary.relevant += 1
                log_stage(
                    logger,
                    STAGE_CLASSIFY,
                    "article_id=%s category=%s relevant=%s topics=%s",
                    article.id,
                    classification.category.value,
                    relevance.relevant,
                    ",".join(t.value for t in topics) or "-",
                )

                breakdown = score_article(
                    article,
                    category=classification.category.value,
                    relevance=relevance,
                    scoring=scoring,
                )
                self.repo.upsert_item_score(
                    article,
                    recency=breakdown.recency,
                    credibility=breakdown.credibility,
                    relevance=breakdown.relevance,
                    novelty=breakdown.novelty,
                    technical_significance=breakdown.technical_significance,
                    industry_impact=breakdown.industry_impact,
                    research_significance=breakdown.research_significance,
                    weighted_total=breakdown.weighted_total,
                    explanation_json=breakdown.explanation,
                )
                article.processing_status = ProcessingStatus.SCORED.value
                summary.scored += 1
                totals.append(breakdown.weighted_total)
                log_stage(
                    logger,
                    STAGE_SCORE,
                    "article_id=%s total=%s recency=%s credibility=%s relevance=%s",
                    article.id,
                    breakdown.weighted_total,
                    breakdown.recency,
                    breakdown.credibility,
                    breakdown.relevance,
                )
            except Exception as exc:  # noqa: BLE001
                article.processing_status = ProcessingStatus.FAILED.value
                article.processing_error = str(exc)
                summary.errors.append(f"article {article.id}: {exc}")
                log_stage(logger, STAGE_SCORE, "failed article_id=%s error=%s", article.id, exc, level=40)

        self.session.flush()
        summary.average_score = round(sum(totals) / len(totals), 2) if totals else 0.0
        status = PipelineRunStatus.PARTIAL if summary.errors else PipelineRunStatus.SUCCESS
        self.repo.finish_pipeline_run(
            run,
            status=status,
            current_stage=STAGE_SCORE,
            successful_sources=0,
            failed_sources=0,
            articles_collected=summary.classified,
            research_papers_count=0,
            duplicates_removed=0,
            relevant_articles=summary.relevant,
            average_importance=summary.average_score,
            error_summary="\n".join(summary.errors) if summary.errors else None,
        )
        log_stage(
            logger,
            STAGE_SCORE,
            "finished classified=%s scored=%s relevant=%s avg=%s",
            summary.classified,
            summary.scored,
            summary.relevant,
            summary.average_score,
        )
        return summary
