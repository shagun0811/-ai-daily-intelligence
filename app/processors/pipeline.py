"""Phase 3: extract → clean → normalize → cluster duplicates. No LLM."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.config.logging import (
    STAGE_CLEAN,
    STAGE_DEDUP,
    STAGE_EMBED,
    STAGE_EXTRACT,
    get_logger,
    log_stage,
)
from app.config.settings import get_settings
from app.config.yaml_loader import load_pipeline
from app.database.enums import ClusterMemberRole, PipelineRunStatus, ProcessingStatus
from app.database.models import Article
from app.database.repository import Repository
from app.processors.cleaner import clean_text
from app.processors.deduplicator import choose_primary, cluster_articles, find_duplicate_pairs
from app.processors.embedder import get_embedder
from app.processors.extractor import extract_full_text, should_extract_full_text
from app.processors.normalizer import embedding_text, normalize_title_for_dedup
from app.utils.hashing import content_hash
from app.utils.urls import canonicalize_url

logger = get_logger(__name__)


@dataclass
class ProcessingSummary:
    cleaned: int = 0
    extracted: int = 0
    extract_failed: int = 0
    skipped_already_clean: int = 0
    clusters: int = 0
    grouped_as_supporting: int = 0
    skipped_recluster: int = 0
    errors: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        lines = [
            f"Cleaned: {self.cleaned}",
            f"Full-text extracted: {self.extracted}",
            f"Extraction failed (kept snippet): {self.extract_failed}",
            f"Already clean (skipped): {self.skipped_already_clean}",
            f"Story clusters: {self.clusters}",
            f"Grouped as supporting sources: {self.grouped_as_supporting}",
            f"Skipped recluster (no new items): {self.skipped_recluster}",
        ]
        if self.errors:
            lines.append("Errors:")
            lines.extend(f"  - {error}" for error in self.errors)
        return "\n".join(lines)


class ContentProcessor:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = Repository(session)

    def run(self) -> ProcessingSummary:
        settings = get_settings()
        pipeline = load_pipeline()
        summary = ProcessingSummary()
        run = self.repo.create_pipeline_run(current_stage=STAGE_EXTRACT)

        pending = self.repo.list_articles_by_status([ProcessingStatus.COLLECTED.value])
        log_stage(logger, STAGE_EXTRACT, "pending=%s", len(pending))
        extracts_used = 0
        for article in pending:
            try:
                extracted = False
                if (
                    settings.extract_full_text
                    and extracts_used < settings.max_full_text_extracts
                    and should_extract_full_text(
                        url=article.url,
                        item_kind=article.item_kind,
                        cleaned_text=article.cleaned_text,
                        min_chars=settings.min_cleaned_text_chars,
                    )
                ):
                    full = extract_full_text(article.url, timeout=settings.http_timeout_seconds)
                    extracts_used += 1
                    if full and len(full) > len(article.cleaned_text or ""):
                        article.raw_text = full
                        article.cleaned_text = clean_text(full, article.description)
                        extracted = True
                        summary.extracted += 1
                    else:
                        summary.extract_failed += 1
                        article.cleaned_text = clean_text(article.cleaned_text, article.description)
                else:
                    article.cleaned_text = clean_text(article.cleaned_text, article.description)

                article.canonical_url = canonicalize_url(article.url)
                article.normalized_title = normalize_title_for_dedup(article.title)
                article.content_hash = content_hash(article.cleaned_text or "", article.url)
                article.processing_status = ProcessingStatus.CLEANED.value
                article.processing_error = None
                summary.cleaned += 1
                log_stage(
                    logger,
                    STAGE_CLEAN,
                    "article_id=%s extracted=%s chars=%s",
                    article.id,
                    extracted,
                    len(article.cleaned_text or ""),
                )
            except Exception as exc:  # noqa: BLE001
                article.processing_status = ProcessingStatus.FAILED.value
                article.processing_error = str(exc)
                summary.errors.append(f"article {article.id}: {exc}")
                log_stage(logger, STAGE_CLEAN, "failed article_id=%s error=%s", article.id, exc, level=40)

        self.session.flush()
        already = self.repo.list_articles_by_status(
            [ProcessingStatus.CLEANED.value, ProcessingStatus.DEDUPLICATED.value]
        )
        summary.skipped_already_clean = max(0, len(already) - summary.cleaned)

        clustered = self._deduplicate(
            already,
            title_threshold=settings.title_similarity_threshold or pipeline.title_similarity_threshold,
            semantic_threshold=settings.semantic_duplicate_threshold or pipeline.semantic_duplicate_threshold,
        )
        summary.clusters = clustered[0]
        summary.grouped_as_supporting = clustered[1]
        summary.skipped_recluster = clustered[2]

        status = PipelineRunStatus.PARTIAL if summary.errors else PipelineRunStatus.SUCCESS
        if not already and summary.cleaned == 0:
            status = PipelineRunStatus.SUCCESS
        self.repo.finish_pipeline_run(
            run,
            status=status,
            current_stage=STAGE_DEDUP,
            successful_sources=0,
            failed_sources=0,
            articles_collected=summary.cleaned,
            research_papers_count=0,
            duplicates_removed=summary.grouped_as_supporting,
            error_summary="\n".join(summary.errors) if summary.errors else None,
        )
        log_stage(
            logger,
            STAGE_DEDUP,
            "finished cleaned=%s clusters=%s supporting=%s",
            summary.cleaned,
            summary.clusters,
            summary.grouped_as_supporting,
        )
        return summary

    def _deduplicate(
        self,
        articles: list[Article],
        *,
        title_threshold: float,
        semantic_threshold: float,
    ) -> tuple[int, int, int]:
        if not articles:
            return 0, 0, 0
        newly_cleaned = [
            article
            for article in articles
            if article.processing_status == ProcessingStatus.CLEANED.value
        ]
        if not newly_cleaned:
            log_stage(logger, STAGE_DEDUP, "skipped reclustering already_deduplicated=%s", len(articles))
            return 0, 0, len(articles)

        embedder = get_embedder()
        texts = [embedding_text(article.title, article.cleaned_text) for article in articles]
        log_stage(logger, STAGE_EMBED, "encoding n=%s model=%s", len(texts), embedder.model_name)
        vectors = embedder.encode(texts)
        for article, vector in zip(articles, vectors, strict=True):
            self.repo.upsert_embedding(
                article,
                model_name=embedder.model_name,
                content_hash=article.content_hash or "",
                dimension=int(vector.shape[0]),
            )

        pairs = find_duplicate_pairs(
            articles,
            vectors=vectors,
            title_threshold=title_threshold,
            semantic_threshold=semantic_threshold,
        )
        groups = cluster_articles(articles, pairs)
        new_ids = {article.id for article in newly_cleaned}

        cluster_count = 0
        supporting = 0
        for group in groups:
            newcomers = [article for article in group if article.id in new_ids]
            for article in newcomers:
                article.processing_status = ProcessingStatus.DEDUPLICATED.value
            if not newcomers:
                continue
            if len(group) < 2:
                continue

            existing_cluster = _cluster_for_existing(group, new_ids)
            if existing_cluster is not None:
                existing_ids = {member.article_id for member in existing_cluster.members}
                for article in newcomers:
                    if article.id in existing_ids:
                        continue
                    self.repo.add_cluster_member(existing_cluster, article, ClusterMemberRole.SUPPORTING)
                    supporting += 1
                    self.repo.add_processing_result(
                        article,
                        stage="DEDUP",
                        model_used=embedder.model_name,
                        content_hash=article.content_hash,
                        output_json={
                            "cluster_id": existing_cluster.id,
                            "role": ClusterMemberRole.SUPPORTING.value,
                            "primary_article_id": existing_cluster.primary_article_id,
                        },
                    )
                continue

            primary = choose_primary(group)
            cluster = self.repo.create_story_cluster(
                event_title=primary.title,
                primary_article=primary,
                cluster_date=primary.published_at,
            )
            cluster_count += 1
            for article in group:
                role = (
                    ClusterMemberRole.PRIMARY
                    if article.id == primary.id
                    else ClusterMemberRole.SUPPORTING
                )
                self.repo.add_cluster_member(cluster, article, role)
                if role is ClusterMemberRole.SUPPORTING:
                    supporting += 1
                self.repo.add_processing_result(
                    article,
                    stage="DEDUP",
                    model_used=embedder.model_name,
                    content_hash=article.content_hash,
                    output_json={
                        "cluster_id": cluster.id,
                        "role": role.value,
                        "primary_article_id": primary.id,
                    },
                )
        self.session.flush()
        return cluster_count, supporting, 0


def _cluster_for_existing(group: list[Article], new_ids: set[int]):
    for article in group:
        if article.id in new_ids:
            continue
        for membership in article.cluster_memberships:
            if membership.cluster is not None:
                return membership.cluster
    return None
