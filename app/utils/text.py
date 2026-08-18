"""Light text cleanup for collected items. Deeper cleaning is Phase 3."""

from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup

_WHITESPACE = re.compile(r"\s+")


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(value)
    soup = BeautifulSoup(text, "lxml")
    cleaned = soup.get_text(separator=" ", strip=True)
    return normalize_whitespace(cleaned)


def normalize_whitespace(value: str | None) -> str:
    if not value:
        return ""
    return _WHITESPACE.sub(" ", value).strip()


def normalize_title(value: str | None) -> str:
    return normalize_whitespace(value).lower()


def truncate(value: str | None, max_length: int) -> str:
    text = value or ""
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"
