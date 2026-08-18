"""URL and title normalization tests. No network."""

from app.processors.normalizer import normalize_title_for_dedup
from app.utils.urls import canonicalize_url


def test_canonicalize_url_strips_tracking_and_fragment() -> None:
    raw = "HTTPS://www.Example.com/ai/post/?utm_source=twitter&fbclid=abc#section"
    assert canonicalize_url(raw) == "https://example.com/ai/post"

    trailing = "https://example.com/ai/post/"
    assert canonicalize_url(trailing) == "https://example.com/ai/post"


def test_canonicalize_url_keeps_meaningful_query() -> None:
    raw = "https://arxiv.org/abs/2608.01234?context=cs"
    assert "context=cs" in canonicalize_url(raw)


def test_normalize_title_strips_boilerplate() -> None:
    title = "Breaking: OpenAI releases GPT-5 | TechCrunch"
    assert normalize_title_for_dedup(title) == "openai releases gpt 5"


def test_normalize_title_collapses_punctuation() -> None:
    assert normalize_title_for_dedup("  New AI-Model!!  ") == "new ai model"
