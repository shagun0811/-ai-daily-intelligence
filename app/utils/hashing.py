"""Hashing helpers used for content and cache keys."""

from __future__ import annotations

import hashlib


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def content_hash(cleaned_text: str, url: str) -> str:
    """Stable hash of cleaned body plus URL so edits and URL variants are visible."""
    return sha256_text(f"{url}\n{cleaned_text}")
