"""Clean collected text. Does not call an LLM."""

from __future__ import annotations

from app.utils.text import normalize_whitespace, strip_html


def clean_text(raw: str | None, fallback: str | None = None) -> str:
    """Strip HTML and collapse whitespace. Prefer raw, then fallback."""
    primary = normalize_whitespace(strip_html(raw))
    if len(primary) >= 40:
        return primary
    secondary = normalize_whitespace(strip_html(fallback))
    return secondary or primary
