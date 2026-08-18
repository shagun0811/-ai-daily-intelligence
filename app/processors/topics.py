"""Map article text to TopicCode values. No LLM."""

from __future__ import annotations

from app.config.taxonomy import TaxonomyConfig, load_taxonomy
from app.database.enums import TopicCode
from app.database.models import Article


def extract_topics(
    article: Article,
    taxonomy: TaxonomyConfig | None = None,
    *,
    limit: int = 6,
) -> list[TopicCode]:
    taxonomy = taxonomy or load_taxonomy()
    text = " ".join(
        [article.title or "", article.description or "", article.cleaned_text or ""]
    ).lower()
    scored: list[tuple[int, TopicCode]] = []
    for code, terms in taxonomy.topic_terms().items():
        hits = sum(1 for term in terms if term in text)
        if hits:
            scored.append((hits, code))
    scored.sort(key=lambda item: (-item[0], item[1].value))
    return [code for _hits, code in scored[:limit]]
