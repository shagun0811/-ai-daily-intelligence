"""AI relevance scoring with keywords. No LLM."""

from __future__ import annotations

from dataclasses import dataclass

from app.config.taxonomy import TaxonomyConfig, load_taxonomy
from app.database.enums import ItemKind
from app.database.models import Article


def _blob(article: Article) -> str:
    parts = [article.title or "", article.description or "", article.cleaned_text or ""]
    return " ".join(parts).lower()


def _clamp(value: float) -> float:
    return max(0.0, min(10.0, value))


@dataclass(frozen=True)
class RelevanceResult:
    score: float
    relevant: bool
    reasons: list[str]


def score_relevance(
    article: Article,
    taxonomy: TaxonomyConfig | None = None,
) -> RelevanceResult:
    taxonomy = taxonomy or load_taxonomy()
    text = _blob(article)
    reasons: list[str] = []
    score = 1.5

    if article.item_kind == ItemKind.RESEARCH_PAPER.value:
        score = 8.0
        reasons.append("research_paper")

    for term in taxonomy.relevance.strong_terms:
        if term.lower() in text:
            score += 1.4
            reasons.append(f"strong:{term}")
    for term in taxonomy.relevance.weak_terms:
        if term.lower() in text:
            score += 0.45
            reasons.append(f"weak:{term}")
    for term in taxonomy.relevance.noise_terms:
        if term.lower() in text:
            score -= 2.5
            reasons.append(f"noise:{term}")

    score = _clamp(score)
    return RelevanceResult(
        score=round(score, 2),
        relevant=score >= taxonomy.relevance.min_score,
        reasons=reasons[:12],
    )
