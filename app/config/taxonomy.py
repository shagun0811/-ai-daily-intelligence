"""Load keyword taxonomy from config/taxonomy.yaml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from app.config.settings import CONFIG_DIR
from app.config.yaml_loader import load_yaml
from app.database.enums import ClassificationCategory, TopicCode


class RelevanceTaxonomy(BaseModel):
    min_score: float = 4.0
    strong_terms: list[str] = Field(default_factory=list)
    weak_terms: list[str] = Field(default_factory=list)
    noise_terms: list[str] = Field(default_factory=list)


class TaxonomyConfig(BaseModel):
    relevance: RelevanceTaxonomy
    categories: dict[str, list[str]]
    topics: dict[str, list[str]]

    def category_terms(self) -> dict[ClassificationCategory, list[str]]:
        mapping: dict[ClassificationCategory, list[str]] = {}
        for raw_name, terms in self.categories.items():
            mapping[ClassificationCategory(raw_name)] = [term.lower() for term in terms]
        return mapping

    def topic_terms(self) -> dict[TopicCode, list[str]]:
        mapping: dict[TopicCode, list[str]] = {}
        for raw_name, terms in self.topics.items():
            mapping[TopicCode(raw_name)] = [term.lower() for term in terms]
        return mapping


@lru_cache(maxsize=1)
def load_taxonomy(config_dir: Path | None = None) -> TaxonomyConfig:
    directory = config_dir or CONFIG_DIR
    return TaxonomyConfig.model_validate(load_yaml(directory / "taxonomy.yaml"))


def clear_taxonomy_cache() -> None:
    load_taxonomy.cache_clear()
