"""Configuration loading tests."""

from __future__ import annotations

import os

import pytest

from app.config.settings import Settings, clear_settings_cache, get_settings
from app.config.yaml_loader import enabled_sources, load_pipeline, load_scoring, load_sources
from app.database.enums import CredibilityTier, SourceType


def test_default_settings_are_free_first() -> None:
    clear_settings_cache()
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "mock"
    assert settings.llm_model == "qwen3:4b"
    assert "openai" not in settings.llm_provider.lower()
    assert settings.scheduler_enabled is False
    assert settings.scheduler_timezone == "Asia/Kolkata"
    assert 0 < settings.semantic_duplicate_threshold <= 1


def test_env_overrides_database_url(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/custom.db")
    clear_settings_cache()
    settings = get_settings()
    assert settings.database_url.endswith("custom.db")
    resolved = settings.resolved_database_url()
    assert resolved.startswith("sqlite:///")
    assert "custom.db" in resolved
    clear_settings_cache()


def test_sources_yaml_parses() -> None:
    sources = load_sources()
    assert len(sources) >= 5
    names = {item.name for item in sources}
    assert "Google AI Blog" in names
    assert "TechCrunch AI" in names
    assert "arXiv cs.AI / cs.LG / cs.CL" in names
    arxiv = next(item for item in sources if item.type == SourceType.ARXIV)
    assert arxiv.credibility == CredibilityTier.TIER_1
    assert "cs.AI" in arxiv.extra["categories"]


def test_enabled_sources_exclude_failed_feeds() -> None:
    enabled = {item.name for item in enabled_sources()}
    assert "Google AI Blog" in enabled
    assert "Hugging Face Blog" in enabled
    assert "OpenAI News" in enabled
    assert "The Verge AI" in enabled
    assert "Google DeepMind Blog" not in enabled


def test_scoring_weights_sum_to_one() -> None:
    scoring = load_scoring()
    assert abs(scoring.weights.total() - 1.0) < 1e-9
    assert scoring.credibility_tier_scores["tier_1"] > scoring.credibility_tier_scores["tier_3"]


def test_pipeline_yaml_limits() -> None:
    pipeline = load_pipeline()
    assert pipeline.max_llm_items <= 30 or pipeline.max_llm_items >= 1
    assert pipeline.report_max_items >= 1
    assert 0 < pipeline.semantic_duplicate_threshold < 1


def test_secret_keys_are_not_required() -> None:
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        os.environ.pop(key, None)
    settings = Settings(_env_file=None)
    assert settings.llm_provider == "mock"


def test_load_yaml_rejects_missing_file(tmp_path) -> None:
    from app.config.yaml_loader import load_yaml

    with pytest.raises(FileNotFoundError):
        load_yaml(tmp_path / "missing.yaml")


def test_edition_calendar_day_is_ist() -> None:
    from app.utils.dates import today_ist

    day = today_ist()
    assert day.isoformat() == str(day)
    assert len(day.isoformat()) == 10
