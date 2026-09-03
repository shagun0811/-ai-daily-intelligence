"""AI relevance scoring with keywords. No LLM."""

from __future__ import annotations

from dataclasses import dataclass

from app.config.taxonomy import TaxonomyConfig, load_taxonomy
from app.database.enums import ItemKind
from app.database.models import Article


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("-", " ").split())


def _blob(article: Article) -> str:
    parts = [article.title or "", article.description or "", article.cleaned_text or ""]
    return _norm(" ".join(parts))


def _clamp(value: float) -> float:
    return max(0.0, min(10.0, value))


_HERO_CATEGORIES = {"PRODUCT", "MODEL_RELEASE", "SAFETY", "POLICY", "BENCHMARK"}


def matches_terms(text: str, terms: list[str]) -> bool:
    blob = _norm(text)
    return any(_norm(term) in blob for term in terms if term)


def is_gossip_text(text: str, taxonomy: TaxonomyConfig | None = None) -> bool:
    taxonomy = taxonomy or load_taxonomy()
    return matches_terms(text, taxonomy.relevance.gossip_terms)


def has_hero_substance(
    text: str,
    category: str = "",
    taxonomy: TaxonomyConfig | None = None,
) -> bool:
    taxonomy = taxonomy or load_taxonomy()
    if (category or "").upper() in _HERO_CATEGORIES:
        return True
    return matches_terms(text, taxonomy.relevance.hero_terms)


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
        score += taxonomy.relevance.paper_bonus
        reasons.append("research_paper")
    else:
        score += taxonomy.relevance.news_bonus
        reasons.append("news_item")

    for term in taxonomy.relevance.strong_terms:
        if _norm(term) in text:
            score += 1.4
            reasons.append(f"strong:{term}")
    for term in taxonomy.relevance.weak_terms:
        if _norm(term) in text:
            score += 0.45
            reasons.append(f"weak:{term}")
    for term in taxonomy.relevance.noise_terms:
        if _norm(term) in text:
            score -= 2.5
            reasons.append(f"noise:{term}")
    if is_gossip_text(text, taxonomy) and not has_hero_substance(text, taxonomy=taxonomy):
        score -= taxonomy.relevance.gossip_penalty
        reasons.append("gossip")
    for term in taxonomy.relevance.niche_terms:
        if _norm(term) in text:
            score -= 3.0
            reasons.append(f"niche:{term}")

    score = _clamp(score)
    return RelevanceResult(
        score=round(score, 2),
        relevant=score >= taxonomy.relevance.min_score,
        reasons=reasons[:12],
    )
