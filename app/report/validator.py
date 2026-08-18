"""Light provenance and hallucination checks. No extra LLM call."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.database.models import Article

_NOT_STATED = re.compile(r"not stated in the source", re.IGNORECASE)
_NUMBER = re.compile(r"(?<![A-Za-z./])(\d+(?:,\d{3})*(?:\.\d+)?%?)(?![A-Za-z])")
_QUOTE = re.compile(r"[\"“]([^\"”]{8,})[\"”]")
_TINY = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "0"}


@dataclass
class ValidationResult:
    ok: bool
    flags: list[str] = field(default_factory=list)
    provenance_source_name: str = ""
    provenance_source_url: str = ""
    provenance_published_at: str | None = None
    insufficient_information: bool = False


def source_blob(article: Article) -> str:
    return " ".join(
        part
        for part in (
            article.title,
            article.description,
            article.cleaned_text,
            getattr(article.research_paper, "abstract", None) if article.research_paper else None,
        )
        if part
    )


def extract_numbers(text: str) -> set[str]:
    found: set[str] = set()
    for match in _NUMBER.findall(text or ""):
        normalized = match.replace(",", "")
        if normalized in _TINY:
            continue
        found.add(normalized.lower())
    return found


def validate_item(article: Article, summary: dict) -> ValidationResult:
    """Check provenance and that claimed numbers/quotes appear in the source."""
    flags: list[str] = []
    provenance = summary.get("provenance") if isinstance(summary.get("provenance"), dict) else {}
    source_name = str(provenance.get("source_name") or getattr(article.source, "name", "") or "")
    source_url = str(provenance.get("source_url") or article.url or "")
    published = provenance.get("published_at")
    if published is None and article.published_at is not None:
        published = article.published_at.isoformat()
    insufficient = bool(provenance.get("insufficient_information"))

    if not source_name:
        flags.append("missing_source_name")
    if not source_url:
        flags.append("missing_source_url")
    elif source_url.rstrip("/") != (article.url or "").rstrip("/"):
        flags.append("source_url_mismatch")
        source_url = article.url

    blob = source_blob(article)
    claimed = _claim_text(summary)
    source_numbers = extract_numbers(blob)
    for number in sorted(extract_numbers(claimed) - source_numbers):
        flags.append(f"number_not_in_source:{number}")
    source_lower = blob.lower()
    for quote in _QUOTE.findall(claimed):
        if quote.lower() not in source_lower:
            flags.append("quote_not_in_source")

    if insufficient:
        flags.append("insufficient_information")

    return ValidationResult(
        ok=not any(flag.startswith("number_not_in_source") or flag == "quote_not_in_source" for flag in flags)
        and "missing_source_url" not in flags,
        flags=flags,
        provenance_source_name=source_name or getattr(article.source, "name", "unknown"),
        provenance_source_url=source_url or article.url,
        provenance_published_at=str(published) if published else None,
        insufficient_information=insufficient,
    )


def _claim_text(summary: dict) -> str:
    parts: list[str] = []
    for key, value in summary.items():
        if key in {"provenance", "schema", "cache_hit", "provider", "facts", "interpretation"}:
            continue
        if isinstance(value, str) and not _NOT_STATED.search(value):
            parts.append(value)
    facts = summary.get("facts") or []
    if isinstance(facts, list):
        parts.extend(str(item) for item in facts)
    return " ".join(parts)
