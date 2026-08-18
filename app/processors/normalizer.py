"""Title and body normalization. No LLM."""

from __future__ import annotations

import re

from app.utils.text import normalize_whitespace, strip_html

_PREFIX = re.compile(
    r"^(breaking|exclusive|update|opinion|analysis|live|watch)\s*:\s*",
    re.IGNORECASE,
)
_SITE_SUFFIX = re.compile(r"\s+[\|\-–—]\s+[A-Za-z0-9 .&']{2,40}$")
_NON_ALNUM = re.compile(r"[^\w\s]+", re.UNICODE)


def normalize_title_for_dedup(title: str | None) -> str:
    """Stable title key: strip boilerplate, punctuation, and site-name suffixes."""
    text = strip_html(title)
    text = _PREFIX.sub("", text)
    text = _SITE_SUFFIX.sub("", text)
    text = _NON_ALNUM.sub(" ", text.lower())
    return normalize_whitespace(text)


def embedding_text(title: str | None, body: str | None, *, body_limit: int = 500) -> str:
    body_text = normalize_whitespace(body)[:body_limit]
    return normalize_whitespace(f"{title or ''}\n{body_text}")
