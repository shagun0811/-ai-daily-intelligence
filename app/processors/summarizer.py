"""Summarize high-value items through LLMProvider. Never calls Ollama directly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config.logging import STAGE_SUMMARIZE, get_logger, log_stage
from app.config.settings import get_settings
from app.config.taxonomy import load_taxonomy
from app.database.enums import ClusterMemberRole, PipelineRunStatus, ProcessingStatus
from app.database.models import Article
from app.database.repository import Repository
from app.llm.base import LLMError, LLMProvider
from app.llm.factory import get_llm_provider
from app.llm.prompts import (
    INSUFFICIENT_TEXT_CHARS,
    SYSTEM_PROMPT,
    build_user_prompt,
    schema_for,
)
from app.llm.schemas import CompanySummary, NewsSummary, ResearchSummary
from app.utils.hashing import content_hash, sha256_text

logger = get_logger(__name__)

_STAGE = "SUMMARIZE"
_SCHEMA_MODELS = {
    "news": NewsSummary,
    "research": ResearchSummary,
    "company": CompanySummary,
}


@dataclass
class SummarizeSummary:
    candidates: int = 0
    summarized: int = 0
    cache_hits: int = 0
    skipped_already: int = 0
    skipped_irrelevant: int = 0
    skipped_supporting: int = 0
    skipped_cap: int = 0
    errors: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        lines = [
            f"Candidates considered: {self.candidates}",
            f"Summarized: {self.summarized}",
            f"Cache hits: {self.cache_hits}",
            f"Already summarized (skipped): {self.skipped_already}",
            f"Skipped irrelevant: {self.skipped_irrelevant}",
            f"Skipped supporting duplicates: {self.skipped_supporting}",
            f"Skipped by MAX_LLM_ITEMS cap: {self.skipped_cap}",
        ]
        if self.errors:
            lines.append("Errors:")
            lines.extend(f"  - {error}" for error in self.errors)
        return "\n".join(lines)


class Summarizer:
    def __init__(self, session: Session, provider: LLMProvider | None = None) -> None:
        self.session = session
        self.repo = Repository(session)
        self.provider = provider or get_llm_provider()
        self.settings = get_settings()

    def run(self) -> SummarizeSummary:
        summary = SummarizeSummary()
        run = self.repo.create_pipeline_run(current_stage=STAGE_SUMMARIZE)
        selected = self._select_items(summary)
        log_stage(
            logger,
            STAGE_SUMMARIZE,
            "provider=%s model=%s selected=%s cap=%s",
            self.provider.provider_name,
            self.provider.model,
            len(selected),
            self.settings.max_llm_items,
        )
        for article in selected:
            try:
                self._summarize_article(article, summary)
            except LLMError as exc:
                article.processing_error = str(exc)
                summary.errors.append(f"article {article.id}: {exc}")
                log_stage(
                    logger,
                    STAGE_SUMMARIZE,
                    "failed article_id=%s error=%s",
                    article.id,
                    exc,
                    level=40,
                )
            except Exception as exc:  # noqa: BLE001
                article.processing_error = str(exc)
                summary.errors.append(f"article {article.id}: {exc}")
                log_stage(
                    logger,
                    STAGE_SUMMARIZE,
                    "failed article_id=%s error=%s",
                    article.id,
                    exc,
                    level=40,
                )

        self.session.flush()
        status = PipelineRunStatus.PARTIAL if summary.errors else PipelineRunStatus.SUCCESS
        self.repo.finish_pipeline_run(
            run,
            status=status,
            current_stage=STAGE_SUMMARIZE,
            successful_sources=0,
            failed_sources=0,
            articles_collected=0,
            research_papers_count=0,
            relevant_articles=summary.candidates,
            final_selected=summary.summarized,
            error_summary="\n".join(summary.errors) if summary.errors else None,
        )
        log_stage(
            logger,
            STAGE_SUMMARIZE,
            "finished summarized=%s cache_hits=%s errors=%s",
            summary.summarized,
            summary.cache_hits,
            len(summary.errors),
        )
        return summary

    def _select_items(self, summary: SummarizeSummary) -> list[Article]:
        already = self.repo.list_articles_by_status([ProcessingStatus.SUMMARIZED.value])
        summary.skipped_already = len(already)

        scored = self.repo.list_articles_by_status([ProcessingStatus.SCORED.value])
        taxonomy = load_taxonomy()
        min_score = taxonomy.relevance.min_score
        eligible: list[Article] = []
        for article in scored:
            if _is_supporting(article):
                summary.skipped_supporting += 1
                continue
            if not _is_relevant(article, min_score):
                summary.skipped_irrelevant += 1
                continue
            eligible.append(article)

        eligible.sort(key=lambda item: _weighted_total(item), reverse=True)
        summary.candidates = len(eligible)
        cap = self.settings.max_llm_items
        if len(eligible) > cap:
            summary.skipped_cap = len(eligible) - cap
            eligible = eligible[:cap]
        return eligible

    def _summarize_article(self, article: Article, summary: SummarizeSummary) -> None:
        kind = schema_for(article)
        body = article.cleaned_text or article.description or article.title or ""
        hash_value = article.content_hash or content_hash(body, article.url)
        prompt = build_user_prompt(article)
        prompt_hash = sha256_text(
            f"{self.provider.provider_name}\n{self.provider.model}\n{SYSTEM_PROMPT}\n{prompt}"
        )

        existing = self.repo.get_processing_result(
            article,
            stage=_STAGE,
            content_hash=hash_value,
            model_used=self.provider.model,
        )
        if existing is not None and existing.output_json:
            article.processing_status = ProcessingStatus.SUMMARIZED.value
            summary.skipped_already += 1
            return

        cached = self.repo.get_llm_cache(prompt_hash, self.provider.model)
        if cached is not None and cached.response_json:
            payload = dict(cached.response_json)
            parsed = self._validate(kind, payload, article, body)
            self._persist(article, parsed, hash_value, cache_hit=True)
            summary.cache_hits += 1
            summary.summarized += 1
            return

        payload = self.provider.generate_json(
            prompt,
            system=SYSTEM_PROMPT,
            max_retries=self.settings.llm_max_retries,
        )
        try:
            parsed = self._validate(kind, payload, article, body)
        except ValidationError as exc:
            retry_prompt = (
                prompt
                + "\n\nThe JSON did not match the schema: "
                + str(exc).split("\n", 1)[0]
                + "\nReturn a corrected JSON object."
            )
            payload = self.provider.generate_json(
                retry_prompt,
                system=SYSTEM_PROMPT,
                max_retries=0,
            )
            parsed = self._validate(kind, payload, article, body)

        self.repo.upsert_llm_cache(
            prompt_hash=prompt_hash,
            provider=self.provider.provider_name,
            model=self.provider.model,
            response_json=parsed.model_dump(),
        )
        self._persist(article, parsed, hash_value, cache_hit=False)
        summary.summarized += 1

    def _validate(
        self,
        kind: str,
        payload: dict[str, Any],
        article: Article,
        body: str,
    ) -> NewsSummary | ResearchSummary | CompanySummary:
        attached = _with_provenance(payload, article, body)
        model = _SCHEMA_MODELS[kind]
        return model.model_validate(attached)

    def _persist(
        self,
        article: Article,
        parsed: NewsSummary | ResearchSummary | CompanySummary,
        hash_value: str,
        *,
        cache_hit: bool,
    ) -> None:
        output = parsed.model_dump()
        output["schema"] = schema_for(article)
        output["cache_hit"] = cache_hit
        output["provider"] = self.provider.provider_name
        self.repo.add_processing_result(
            article,
            stage=_STAGE,
            model_used=self.provider.model,
            content_hash=hash_value,
            output_json=output,
        )
        if isinstance(parsed, ResearchSummary) and article.research_paper is not None:
            paper = article.research_paper
            paper.key_contribution = parsed.key_innovation
            paper.methodology = parsed.proposed_approach
            paper.results = parsed.results
            paper.limitations = parsed.limitations
            paper.research_significance = parsed.why_it_matters
        article.processing_status = ProcessingStatus.SUMMARIZED.value
        article.processing_error = None
        log_stage(
            logger,
            STAGE_SUMMARIZE,
            "article_id=%s schema=%s cache_hit=%s insufficient=%s",
            article.id,
            schema_for(article),
            cache_hit,
            parsed.provenance.insufficient_information,
        )


def _is_supporting(article: Article) -> bool:
    return any(link.role == ClusterMemberRole.SUPPORTING.value for link in article.cluster_memberships)


def _is_relevant(article: Article, min_score: float) -> bool:
    if article.score is None:
        return False
    explanation = article.score.explanation_json or {}
    if "relevant" in explanation:
        return bool(explanation["relevant"])
    return article.score.relevance >= min_score


def _weighted_total(article: Article) -> float:
    if article.score is None:
        return 0.0
    return float(article.score.weighted_total)


def _with_provenance(payload: dict[str, Any], article: Article, body: str) -> dict[str, Any]:
    """Overwrite provenance from the article so the model cannot invent a source."""
    attached = dict(payload)
    published = article.published_at.isoformat() if article.published_at else None
    source_name = getattr(article.source, "name", "") or "unknown"
    incoming = attached.get("provenance") if isinstance(attached.get("provenance"), dict) else {}
    insufficient = bool(incoming.get("insufficient_information")) or len(body.strip()) < INSUFFICIENT_TEXT_CHARS
    attached["provenance"] = {
        "source_name": source_name,
        "source_url": article.url,
        "published_at": published,
        "insufficient_information": insufficient,
    }
    return attached
