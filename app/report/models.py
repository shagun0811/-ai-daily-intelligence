"""Structured daily report payload used by Markdown, HTML, and PDF renderers."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class ReportItem(BaseModel):
    article_id: int
    title: str
    summary: str
    why_it_matters: str
    problem: str = ""
    key_contribution: str = ""
    source_name: str
    source_url: str
    published_at: str | None = None
    supporting_sources: list[str] = Field(default_factory=list)
    score: float = 0.0
    category: str = "OTHER"
    schema_name: str = "news"
    validation_flags: list[str] = Field(default_factory=list)
    insufficient_information: bool = False


class DailyReportDocument(BaseModel):
    title: str = "AI Daily Intelligence"
    report_date: date
    executive: list[ReportItem] = Field(default_factory=list)
    developments: list[ReportItem] = Field(default_factory=list)
    research: list[ReportItem] = Field(default_factory=list)
    industry: list[ReportItem] = Field(default_factory=list)
    watch: list[str] = Field(default_factory=list)
    sources: list[tuple[str, str]] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)
