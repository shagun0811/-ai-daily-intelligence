"""Seed taxonomy and YAML sources. Idempotent."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.logging import STAGE_DB, get_logger, log_stage
from app.config.yaml_loader import load_sources
from app.database.enums import TopicCode
from app.database.models import Source, Topic

logger = get_logger(__name__)

_TOPIC_LABELS: dict[TopicCode, str] = {
    TopicCode.LLM: "Large Language Models",
    TopicCode.SLM: "Small Language Models",
    TopicCode.AGENTS: "AI Agents",
    TopicCode.RAG: "Retrieval-Augmented Generation",
    TopicCode.MULTIMODAL: "Multimodal AI",
    TopicCode.COMPUTER_VISION: "Computer Vision",
    TopicCode.ROBOTICS: "Robotics",
    TopicCode.REINFORCEMENT_LEARNING: "Reinforcement Learning",
    TopicCode.GENERATIVE_AI: "Generative AI",
    TopicCode.AI_SAFETY: "AI Safety",
    TopicCode.AI_INFRASTRUCTURE: "AI Infrastructure",
    TopicCode.TRAINING: "Training",
    TopicCode.INFERENCE: "Inference",
    TopicCode.EVALUATION: "Evaluation",
    TopicCode.DATA: "Data",
    TopicCode.AI_FOR_SCIENCE: "AI for Science",
}


def seed_database(session: Session) -> None:
    _seed_topics(session)
    _sync_sources(session)
    session.flush()


def _seed_topics(session: Session) -> None:
    existing = {row.code for row in session.scalars(select(Topic)).all()}
    created = 0
    for code, name in _TOPIC_LABELS.items():
        if code.value in existing:
            continue
        session.add(Topic(code=code.value, name=name))
        created += 1
    if created:
        log_stage(logger, STAGE_DB, "seeded topics count=%s", created)


def _sync_sources(session: Session) -> None:
    """Upsert sources from YAML. Does not fetch content."""
    existing = {row.name: row for row in session.scalars(select(Source)).all()}
    created = 0
    updated = 0
    for config in load_sources():
        row = existing.get(config.name)
        if row is None:
            session.add(
                Source(
                    name=config.name,
                    url=config.url,
                    type=config.type.value,
                    category=config.category,
                    credibility_tier=config.credibility.value,
                    enabled=config.enabled,
                    collection_method=config.collection_method,
                    extra_config=config.extra,
                )
            )
            created += 1
            continue
        row.url = config.url
        row.type = config.type.value
        row.category = config.category
        row.credibility_tier = config.credibility.value
        row.enabled = config.enabled
        row.collection_method = config.collection_method
        row.extra_config = config.extra
        updated += 1
    log_stage(logger, STAGE_DB, "synced sources created=%s updated=%s", created, updated)
