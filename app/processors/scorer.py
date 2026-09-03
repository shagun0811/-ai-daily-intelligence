"""Explainable 0–10 importance scoring. Weights come from config, not code."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.config.yaml_loader import ScoringConfig, load_scoring
from app.database.enums import ClusterMemberRole, ItemKind
from app.database.models import Article
from app.processors.relevance import (
    RelevanceResult,
    has_hero_substance,
    is_gossip_text,
    score_relevance,
)


def _clamp(value: float) -> float:
    return round(max(0.0, min(10.0, value)), 2)


class ScoreBreakdown(BaseModel):
    recency: float
    credibility: float
    relevance: float
    novelty: float
    technical_significance: float
    industry_impact: float
    research_significance: float
    weighted_total: float
    explanation: dict[str, Any] = Field(default_factory=dict)


def recency_score(article: Article, scoring: ScoringConfig, *, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    stamp = article.published_at or article.collected_at or now
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    hours = max(0.0, (now - stamp).total_seconds() / 3600.0)
    full = scoring.recency.full_score_hours
    zero = scoring.recency.zero_score_hours
    if hours <= full:
        return 10.0
    if hours >= zero:
        return 0.0
    return _clamp(10.0 * (1.0 - (hours - full) / (zero - full)))


def credibility_score(article: Article, scoring: ScoringConfig) -> float:
    tier = getattr(article.source, "credibility_tier", "tier_2")
    return _clamp(float(scoring.credibility_tier_scores.get(tier, 5.0)))


def novelty_score(article: Article, recency: float) -> tuple[float, str]:
    roles = {link.role for link in article.cluster_memberships}
    if ClusterMemberRole.SUPPORTING.value in roles:
        return _clamp(3.0 + 0.15 * recency), "supporting_source"
    if ClusterMemberRole.PRIMARY.value in roles:
        return _clamp(6.5 + 0.2 * recency), "cluster_primary"
    return _clamp(7.2 + 0.2 * recency), "singleton"


def technical_score(article: Article, text: str) -> float:
    score = 3.5
    if article.item_kind == ItemKind.RESEARCH_PAPER.value:
        score = 4.5
    terms = (
        "architecture",
        "benchmark",
        "parameter",
        "weights",
        "algorithm",
        "sota",
        "transformer",
        "dataset",
        "latency",
        "training",
        "self-improving",
        "agentic",
    )
    score += sum(0.6 for term in terms if term in text)
    return _clamp(score)


def industry_score(article: Article, text: str, category: str) -> float:
    is_paper = article.item_kind == ItemKind.RESEARCH_PAPER.value or category == "RESEARCH"
    score = 3.0
    if not is_paper:
        score += 1.5
    if category in {"PRODUCT", "MODEL_RELEASE", "FUNDING", "ACQUISITION", "COMPANY"}:
        score += 2.5
    terms = ("launch", "available", "enterprise", "customer", "partnership", "revenue", "api")
    score += sum(0.5 for term in terms if term in text)
    if is_paper:
        score -= 1.0
    if is_gossip_text(text) and not has_hero_substance(text, category):
        score -= 2.2
    return _clamp(score)


def research_score(article: Article, text: str, category: str) -> float:
    if article.item_kind == ItemKind.RESEARCH_PAPER.value or category == "RESEARCH":
        score = 5.0
    else:
        score = 2.0
    terms = ("abstract", "method", "arxiv", "paper", "results", "limitation")
    score += sum(0.4 for term in terms if term in text)
    return _clamp(score)


def score_article(
    article: Article,
    *,
    category: str,
    relevance: RelevanceResult | None = None,
    scoring: ScoringConfig | None = None,
    now: datetime | None = None,
) -> ScoreBreakdown:
    scoring = scoring or load_scoring()
    relevance = relevance or score_relevance(article)
    text = " ".join(
        [article.title or "", article.description or "", article.cleaned_text or ""]
    ).lower()

    recency = recency_score(article, scoring, now=now)
    credibility = credibility_score(article, scoring)
    novelty, novelty_reason = novelty_score(article, recency)
    technical = technical_score(article, text)
    industry = industry_score(article, text, category)
    research = research_score(article, text, category)

    weights = scoring.weights
    total = (
        weights.recency * recency
        + weights.credibility * credibility
        + weights.relevance * relevance.score
        + weights.novelty * novelty
        + weights.technical_significance * technical
        + weights.industry_impact * industry
        + weights.research_significance * research
    )
    return ScoreBreakdown(
        recency=recency,
        credibility=credibility,
        relevance=relevance.score,
        novelty=novelty,
        technical_significance=technical,
        industry_impact=industry,
        research_significance=research,
        weighted_total=_clamp(total),
        explanation={
            "novelty_reason": novelty_reason,
            "relevance_reasons": relevance.reasons,
            "relevant": relevance.relevant,
            "weights": weights.model_dump(),
        },
    )
