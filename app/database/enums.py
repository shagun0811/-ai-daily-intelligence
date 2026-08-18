"""Enumerations stored as strings in SQLite."""

from __future__ import annotations

from enum import StrEnum


class SourceType(StrEnum):
    RSS = "rss"
    API = "api"
    ARXIV = "arxiv"
    WEBPAGE = "webpage"


class CredibilityTier(StrEnum):
    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"


class ProcessingStatus(StrEnum):
    COLLECTED = "COLLECTED"
    CLEANED = "CLEANED"
    DEDUPLICATED = "DEDUPLICATED"
    CLASSIFIED = "CLASSIFIED"
    SCORED = "SCORED"
    SUMMARIZED = "SUMMARIZED"
    VALIDATED = "VALIDATED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class ItemKind(StrEnum):
    ARTICLE = "article"
    RESEARCH_PAPER = "research_paper"


class ClassificationCategory(StrEnum):
    NEWS = "NEWS"
    RESEARCH = "RESEARCH"
    COMPANY = "COMPANY"
    PRODUCT = "PRODUCT"
    MODEL_RELEASE = "MODEL_RELEASE"
    OPEN_SOURCE = "OPEN_SOURCE"
    FUNDING = "FUNDING"
    ACQUISITION = "ACQUISITION"
    BENCHMARK = "BENCHMARK"
    POLICY = "POLICY"
    SAFETY = "SAFETY"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    OTHER = "OTHER"


class TopicCode(StrEnum):
    LLM = "LLM"
    SLM = "SLM"
    AGENTS = "AGENTS"
    RAG = "RAG"
    MULTIMODAL = "MULTIMODAL"
    COMPUTER_VISION = "COMPUTER_VISION"
    ROBOTICS = "ROBOTICS"
    REINFORCEMENT_LEARNING = "REINFORCEMENT_LEARNING"
    GENERATIVE_AI = "GENERATIVE_AI"
    AI_SAFETY = "AI_SAFETY"
    AI_INFRASTRUCTURE = "AI_INFRASTRUCTURE"
    TRAINING = "TRAINING"
    INFERENCE = "INFERENCE"
    EVALUATION = "EVALUATION"
    DATA = "DATA"
    AI_FOR_SCIENCE = "AI_FOR_SCIENCE"


class ClusterMemberRole(StrEnum):
    PRIMARY = "primary"
    SUPPORTING = "supporting"


class PipelineRunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class FetchStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
