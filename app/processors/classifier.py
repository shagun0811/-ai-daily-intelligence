"""Rule-based classification. Phase 5 summarizes; it does not replace these labels."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.config.taxonomy import TaxonomyConfig, load_taxonomy
from app.database.enums import ClassificationCategory, ItemKind
from app.database.models import Article

_PRIORITY = [
    ClassificationCategory.ACQUISITION,
    ClassificationCategory.FUNDING,
    ClassificationCategory.MODEL_RELEASE,
    ClassificationCategory.OPEN_SOURCE,
    ClassificationCategory.BENCHMARK,
    ClassificationCategory.POLICY,
    ClassificationCategory.SAFETY,
    ClassificationCategory.INFRASTRUCTURE,
    ClassificationCategory.PRODUCT,
    ClassificationCategory.COMPANY,
    ClassificationCategory.RESEARCH,
    ClassificationCategory.NEWS,
]


class ClassificationResult(BaseModel):
    category: ClassificationCategory
    confidence: float = Field(ge=0.0, le=1.0)
    matched_terms: list[str] = Field(default_factory=list)
    method: str = "rules"


def _blob(article: Article) -> str:
    return " ".join(
        [article.title or "", article.description or "", article.cleaned_text or ""]
    ).lower()


def classify_article(
    article: Article,
    taxonomy: TaxonomyConfig | None = None,
) -> ClassificationResult:
    taxonomy = taxonomy or load_taxonomy()
    if article.item_kind == ItemKind.RESEARCH_PAPER.value:
        return ClassificationResult(
            category=ClassificationCategory.RESEARCH,
            confidence=0.9,
            matched_terms=["research_paper"],
            method="rules",
        )

    text = _blob(article)
    scores: dict[ClassificationCategory, list[str]] = {}
    for category, terms in taxonomy.category_terms().items():
        hits = [term for term in terms if term in text]
        if hits:
            scores[category] = hits

    if not scores:
        return ClassificationResult(
            category=ClassificationCategory.OTHER,
            confidence=0.25,
            matched_terms=[],
            method="rules",
        )

    def rank(item: tuple[ClassificationCategory, list[str]]) -> tuple[int, int]:
        category, hits = item
        try:
            priority = _PRIORITY.index(category)
        except ValueError:
            priority = 99
        return (-len(hits), priority)

    category, hits = sorted(scores.items(), key=rank)[0]
    confidence = min(0.35 + 0.15 * len(hits), 0.85)
    return ClassificationResult(
        category=category,
        confidence=round(confidence, 2),
        matched_terms=hits[:8],
        method="rules",
    )
