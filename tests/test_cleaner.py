"""Cleaning and extraction-gate tests. No live websites."""

from app.processors.cleaner import clean_text
from app.processors.extractor import should_extract_full_text


def test_clean_text_strips_html_and_whitespace() -> None:
    raw = "<p>Hello   <b>world</b></p>\n\n"
    assert clean_text(raw) == "Hello world"


def test_clean_text_uses_fallback_when_raw_is_tiny() -> None:
    assert clean_text("<p>Hi</p>", "A longer fallback description here") == (
        "A longer fallback description here"
    )


def test_should_not_extract_research_papers_or_long_text() -> None:
    assert should_extract_full_text(
        url="https://techcrunch.com/story",
        item_kind="research_paper",
        cleaned_text="short",
        min_chars=400,
    ) is False
    assert should_extract_full_text(
        url="https://arxiv.org/abs/2608.01234",
        item_kind="article",
        cleaned_text="short",
        min_chars=400,
    ) is False
    long_text = "word " * 200
    assert should_extract_full_text(
        url="https://techcrunch.com/story",
        item_kind="article",
        cleaned_text=long_text,
        min_chars=400,
    ) is False
    assert should_extract_full_text(
        url="https://techcrunch.com/story",
        item_kind="article",
        cleaned_text="short blurb",
        min_chars=400,
    ) is True
