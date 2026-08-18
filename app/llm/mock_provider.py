"""Deterministic local summaries. Copies source text; does not invent numbers."""

from __future__ import annotations

import json
import re

from app.llm.base import LLMProvider
from app.llm.prompts import INSUFFICIENT_TEXT_CHARS

_NOT_STATED = "Not stated in the source."
_FIELD = re.compile(r"^(TITLE|SOURCE_NAME|SOURCE_URL|PUBLISHED_AT|CATEGORY|SCHEMA):\s*(.*)$", re.MULTILINE)


class MockProvider(LLMProvider):
    """Used in tests and default development. Never calls a network LLM."""

    provider_name = "mock"

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        fields = {match.group(1): match.group(2).strip() for match in _FIELD.finditer(prompt)}
        kind = (fields.get("SCHEMA") or "news").lower()
        source = _source_text(prompt)
        insufficient = len(source) < INSUFFICIENT_TEXT_CHARS
        payload = _summary_payload(
            kind=kind,
            source=source,
            title=fields.get("TITLE") or "",
            source_name=fields.get("SOURCE_NAME") or "unknown",
            source_url=fields.get("SOURCE_URL") or "",
            published_at=fields.get("PUBLISHED_AT") if fields.get("PUBLISHED_AT") != "unknown" else None,
            insufficient=insufficient,
        )
        return json.dumps(payload)


def _source_text(prompt: str) -> str:
    marker = "SOURCE TEXT:"
    start = prompt.find(marker)
    if start < 0:
        return ""
    rest = prompt[start + len(marker) :]
    for stop in ("\nFill provenance", "\nRequired JSON fields"):
        cut = rest.find(stop)
        if cut >= 0:
            rest = rest[:cut]
            break
    return rest.strip()


def _sentences(text: str, limit: int = 2) -> str:
    chunks = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]
    if not chunks:
        return _NOT_STATED
    return " ".join(chunks[:limit])


def _facts(text: str) -> list[str]:
    chunks = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]
    return chunks[:3]


def _summary_payload(
    *,
    kind: str,
    source: str,
    title: str,
    source_name: str,
    source_url: str,
    published_at: str | None,
    insufficient: bool,
) -> dict:
    provenance = {
        "source_name": source_name,
        "source_url": source_url,
        "published_at": published_at,
        "insufficient_information": insufficient,
    }
    if insufficient:
        copied = _NOT_STATED
        facts: list[str] = []
        interpretation = "No interpretation is possible from the short source text."
        why = _NOT_STATED
    else:
        copied = _sentences(source)
        facts = _facts(source)
        interpretation = "Restatement of the source only; not an independent claim."
        why = copied

    if kind == "research":
        return {
            "problem": copied,
            "previous_limitation": _NOT_STATED,
            "proposed_approach": copied,
            "key_innovation": title or copied,
            "results": _NOT_STATED if "result" not in source.lower() else copied,
            "why_it_matters": why,
            "potential_applications": _NOT_STATED,
            "limitations": _NOT_STATED if "limitation" not in source.lower() else copied,
            "facts": facts,
            "interpretation": interpretation,
            "provenance": provenance,
        }
    if kind == "company":
        return {
            "company": source_name,
            "announcement": title or copied,
            "product_or_model": title or _NOT_STATED,
            "capabilities": copied,
            "availability": _NOT_STATED if "available" not in source.lower() else copied,
            "technical_significance": copied,
            "business_significance": copied,
            "facts": facts,
            "interpretation": interpretation,
            "provenance": provenance,
        }
    return {
        "what_happened": copied,
        "who_is_involved": source_name,
        "what_is_new": title or copied,
        "technical_significance": copied,
        "industry_significance": copied,
        "why_it_matters": why,
        "facts": facts,
        "interpretation": interpretation,
        "provenance": provenance,
    }
