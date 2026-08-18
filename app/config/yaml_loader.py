"""Load and validate YAML configuration files."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config.settings import CONFIG_DIR
from app.database.enums import CredibilityTier, SourceType


class SourceConfig(BaseModel):
    """One collectable source from config/sources.yaml."""

    model_config = ConfigDict(extra="forbid")

    name: str
    url: str
    type: SourceType
    category: str
    credibility: CredibilityTier
    enabled: bool = True
    collection_method: str
    extra: dict[str, Any] = Field(default_factory=dict)


class SourcesFile(BaseModel):
    sources: list[SourceConfig]


class ScoringWeights(BaseModel):
    recency: float
    credibility: float
    relevance: float
    novelty: float
    technical_significance: float
    industry_impact: float
    research_significance: float

    @field_validator(
        "recency",
        "credibility",
        "relevance",
        "novelty",
        "technical_significance",
        "industry_impact",
        "research_significance",
    )
    @classmethod
    def _non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("scoring weights must be >= 0")
        return value

    def total(self) -> float:
        return (
            self.recency
            + self.credibility
            + self.relevance
            + self.novelty
            + self.technical_significance
            + self.industry_impact
            + self.research_significance
        )


class RecencyConfig(BaseModel):
    full_score_hours: int = 24
    zero_score_hours: int = 168


class ScoringConfig(BaseModel):
    weights: ScoringWeights
    credibility_tier_scores: dict[str, float]
    recency: RecencyConfig = RecencyConfig()

    @field_validator("weights")
    @classmethod
    def _weights_sum_to_one(cls, weights: ScoringWeights) -> ScoringWeights:
        total = weights.total()
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"scoring weights must sum to 1.0, got {total}")
        return weights


class PipelineConfig(BaseModel):
    max_articles_per_source: int = 40
    max_llm_items: int = 30
    report_max_items: int = 15
    semantic_duplicate_threshold: float = 0.88
    title_similarity_threshold: float = 0.92
    http_timeout_seconds: int = 20
    arxiv_lookback_days: int = 2
    extract_full_text: bool = True
    min_cleaned_text_chars: int = 400
    max_full_text_extracts: int = 25
    target_relevant_items: int = 60
    target_classified_items: int = 30
    target_final_items: int = 12


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing configuration file: {path}")
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping in {path}")
    return data


@lru_cache(maxsize=1)
def load_sources(config_dir: Path | None = None) -> list[SourceConfig]:
    directory = config_dir or CONFIG_DIR
    parsed = SourcesFile.model_validate(load_yaml(directory / "sources.yaml"))
    return parsed.sources


@lru_cache(maxsize=1)
def load_scoring(config_dir: Path | None = None) -> ScoringConfig:
    directory = config_dir or CONFIG_DIR
    return ScoringConfig.model_validate(load_yaml(directory / "scoring.yaml"))


@lru_cache(maxsize=1)
def load_pipeline(config_dir: Path | None = None) -> PipelineConfig:
    directory = config_dir or CONFIG_DIR
    return PipelineConfig.model_validate(load_yaml(directory / "pipeline.yaml"))


def enabled_sources(config_dir: Path | None = None) -> list[SourceConfig]:
    return [source for source in load_sources(config_dir) if source.enabled]


def clear_yaml_cache() -> None:
    load_sources.cache_clear()
    load_scoring.cache_clear()
    load_pipeline.cache_clear()
