"""LLM provider and JSON parsing tests. No live Ollama."""

from __future__ import annotations

import json

import pytest
import requests

from app.config.settings import clear_settings_cache, get_settings
from app.llm.base import LLMError, LLMProvider
from app.llm.factory import get_llm_provider
from app.llm.json_parse import parse_json_object
from app.llm.mock_provider import MockProvider
from app.llm.ollama_provider import OllamaProvider
from app.llm.prompts import SYSTEM_PROMPT, build_user_prompt, schema_for
from app.llm.schemas import NewsSummary, ResearchSummary


def test_parse_json_object_strips_fences() -> None:
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('noise {"a": 2, "b": true} trailing') == {"a": 2, "b": True}


def test_parse_json_object_rejects_empty() -> None:
    with pytest.raises(ValueError):
        parse_json_object("   ")
    with pytest.raises(ValueError):
        parse_json_object("no object here")


def test_mock_provider_is_default(isolated_db) -> None:
    provider = get_llm_provider()
    assert isinstance(provider, MockProvider)
    assert get_settings().llm_model == "qwen3:4b"
    assert provider.model == get_settings().llm_model


def test_factory_rejects_paid_providers(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    clear_settings_cache()
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        get_llm_provider()
    clear_settings_cache()


def test_factory_builds_ollama_without_calling_it(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "qwen3:4b")
    clear_settings_cache()
    provider = get_llm_provider()
    assert isinstance(provider, OllamaProvider)
    assert provider.model == "qwen3:4b"
    clear_settings_cache()


def test_mock_news_json_matches_schema_and_does_not_invent_numbers() -> None:
    source = (
        "Google announced an open-weights language model for researchers. "
        "The blog post describes availability on Hugging Face."
    )
    prompt = (
        "SCHEMA: news\nTITLE: Google open-weights model\nSOURCE_NAME: Google AI Blog\n"
        "SOURCE_URL: https://blog.google/model\nPUBLISHED_AT: 2026-08-16T00:00:00+00:00\n"
        "CATEGORY: NEWS\n\nSOURCE TEXT:\n"
        f"{source}\n\nFill provenance from SOURCE_NAME, SOURCE_URL, and PUBLISHED_AT.\n"
        "Required JSON fields: what_happened"
    )
    raw = MockProvider(model="qwen3:4b").generate(prompt, system=SYSTEM_PROMPT)
    payload = json.loads(raw)
    parsed = NewsSummary.model_validate(payload)
    assert parsed.provenance.source_url == "https://blog.google/model"
    assert parsed.provenance.insufficient_information is False
    dumped = json.dumps(payload)
    assert "98%" not in dumped
    assert "1 billion users" not in dumped
    assert "Google announced" in parsed.what_happened


def test_mock_marks_short_text_insufficient() -> None:
    prompt = (
        "SCHEMA: research\nTITLE: Tiny\nSOURCE_NAME: arXiv\nSOURCE_URL: https://arxiv.org/abs/1\n"
        "PUBLISHED_AT: unknown\nCATEGORY: RESEARCH\n\nSOURCE TEXT:\nShort.\n\n"
        "Fill provenance from SOURCE_NAME, SOURCE_URL, and PUBLISHED_AT.\n"
        "Required JSON fields: problem"
    )
    payload = json.loads(MockProvider(model="qwen3:4b").generate(prompt))
    parsed = ResearchSummary.model_validate(payload)
    assert parsed.provenance.insufficient_information is True
    assert "Not stated" in parsed.results


def test_generate_json_retries_invalid_output() -> None:
    class Flaky(LLMProvider):
        provider_name = "mock"

        def __init__(self) -> None:
            super().__init__("qwen3:4b")
            self.calls = 0

        def generate(self, prompt: str, *, system: str | None = None) -> str:
            self.calls += 1
            if self.calls == 1:
                return "not json"
            return '{"ok": true}'

    provider = Flaky()
    assert provider.generate_json("hello", max_retries=2) == {"ok": True}
    assert provider.calls == 2


def test_ollama_retries_then_returns_content(monkeypatch) -> None:
    calls = {"n": 0}

    class FakeResponse:
        status_code = 200

        def json(self) -> dict:
            return {"message": {"content": '{"what_happened": "ok"}'}}

    def fake_post(url, json=None, timeout=None):
        calls["n"] += 1
        assert "11434" in url
        assert json["model"] == "qwen3:4b"
        assert json["stream"] is False
        if calls["n"] == 1:
            raise requests.ConnectionError("refused")
        return FakeResponse()

    monkeypatch.setattr("app.llm.ollama_provider.requests.post", fake_post)
    monkeypatch.setattr("app.llm.ollama_provider.sleep", lambda *_args, **_kwargs: None)
    provider = OllamaProvider(
        "qwen3:4b",
        base_url="http://127.0.0.1:11434",
        timeout_seconds=5,
        max_retries=2,
    )
    text = provider.generate("summarize this", system=SYSTEM_PROMPT)
    assert "what_happened" in text
    assert calls["n"] == 2


def test_ollama_down_raises_llm_error(monkeypatch) -> None:
    def fake_post(*_args, **_kwargs):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr("app.llm.ollama_provider.requests.post", fake_post)
    monkeypatch.setattr("app.llm.ollama_provider.sleep", lambda *_args, **_kwargs: None)
    provider = OllamaProvider(
        "qwen3:4b",
        base_url="http://127.0.0.1:11434",
        timeout_seconds=1,
        max_retries=1,
    )
    with pytest.raises(LLMError, match="unreachable"):
        provider.generate("hello")


def test_schema_for_research_and_company(db_session) -> None:
    from app.database.repository import Repository

    repo = Repository(db_session)
    source = repo.get_source_by_name("Google AI Blog")
    assert source is not None
    news = repo.create_article(
        source=source,
        title="A story",
        url="https://blog.google/schema-news",
        llm_category="NEWS",
    )
    company = repo.create_article(
        source=source,
        title="Model drop",
        url="https://blog.google/schema-company",
        llm_category="MODEL_RELEASE",
    )
    paper = repo.create_article(
        source=source,
        title="A paper",
        url="https://arxiv.org/abs/schema",
        item_kind="research_paper",
        llm_category="RESEARCH",
    )
    assert schema_for(news) == "news"
    assert schema_for(company) == "company"
    assert schema_for(paper) == "research"
    prompt = build_user_prompt(paper)
    assert "SCHEMA: research" in prompt
    assert "SOURCE_URL: https://arxiv.org/abs/schema" in prompt
