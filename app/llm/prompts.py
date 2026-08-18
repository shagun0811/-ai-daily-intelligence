"""Short prompts. The model may only use the provided source text."""

from __future__ import annotations

from datetime import datetime

from app.database.models import Article

SYSTEM_PROMPT = """You are an AI intelligence analyst.
Use ONLY the source text provided by the user.
Do not invent facts, numbers, quotes, research results, or announcements.
If the source does not contain a detail, write that it is not stated.
Separate facts (copied from the source) from interpretation.
Return one JSON object. No markdown."""

NEWS_FIELDS = (
    "what_happened, who_is_involved, what_is_new, technical_significance, "
    "industry_significance, why_it_matters, facts (string array), interpretation, "
    "provenance {source_name, source_url, published_at, insufficient_information}"
)
RESEARCH_FIELDS = (
    "problem, previous_limitation, proposed_approach, key_innovation, results, "
    "why_it_matters, potential_applications, limitations, facts (string array), "
    "interpretation, provenance {source_name, source_url, published_at, insufficient_information}"
)
COMPANY_FIELDS = (
    "company, announcement, product_or_model, capabilities, availability, "
    "technical_significance, business_significance, facts (string array), "
    "interpretation, provenance {source_name, source_url, published_at, insufficient_information}"
)

SOURCE_CHAR_LIMIT = 3500
INSUFFICIENT_TEXT_CHARS = 80


def truncate_source(text: str, limit: int = SOURCE_CHAR_LIMIT) -> str:
    body = (text or "").strip()
    if len(body) <= limit:
        return body
    return body[: limit - 1].rstrip() + "…"


def schema_for(article: Article) -> str:
    category = (article.llm_category or "").upper()
    if article.item_kind == "research_paper" or category == "RESEARCH":
        return "research"
    if category in {
        "COMPANY",
        "PRODUCT",
        "MODEL_RELEASE",
        "OPEN_SOURCE",
        "FUNDING",
        "ACQUISITION",
    }:
        return "company"
    return "news"


def build_user_prompt(article: Article, *, source_limit: int = SOURCE_CHAR_LIMIT) -> str:
    kind = schema_for(article)
    fields = {"news": NEWS_FIELDS, "research": RESEARCH_FIELDS, "company": COMPANY_FIELDS}[kind]
    published = _format_date(article.published_at)
    source_name = getattr(article.source, "name", "") or "unknown"
    body = truncate_source(
        article.cleaned_text or article.description or article.title or "",
        source_limit,
    )
    return (
        f"SCHEMA: {kind}\n"
        f"TITLE: {article.title}\n"
        f"SOURCE_NAME: {source_name}\n"
        f"SOURCE_URL: {article.url}\n"
        f"PUBLISHED_AT: {published or 'unknown'}\n"
        f"CATEGORY: {article.llm_category or 'OTHER'}\n\n"
        f"SOURCE TEXT:\n{body}\n\n"
        "Fill provenance from SOURCE_NAME, SOURCE_URL, and PUBLISHED_AT.\n"
        f"Required JSON fields: {fields}"
    )


def _format_date(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
