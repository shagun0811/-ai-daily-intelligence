"""Structured LLM outputs. Free-form model text is never stored as-is."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Provenance(BaseModel):
    source_name: str
    source_url: str
    published_at: str | None = None
    insufficient_information: bool = False


class NewsSummary(BaseModel):
    what_happened: str
    who_is_involved: str
    what_is_new: str
    technical_significance: str
    industry_significance: str
    why_it_matters: str
    facts: list[str] = Field(default_factory=list)
    interpretation: str = ""
    provenance: Provenance


class ResearchSummary(BaseModel):
    problem: str
    previous_limitation: str
    proposed_approach: str
    key_innovation: str
    results: str
    why_it_matters: str
    potential_applications: str
    limitations: str
    facts: list[str] = Field(default_factory=list)
    interpretation: str = ""
    provenance: Provenance


class CompanySummary(BaseModel):
    company: str
    announcement: str
    product_or_model: str
    capabilities: str
    availability: str
    technical_significance: str
    business_significance: str
    facts: list[str] = Field(default_factory=list)
    interpretation: str = ""
    provenance: Provenance
