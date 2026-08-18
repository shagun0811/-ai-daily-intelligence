"""Markdown daily report."""

from __future__ import annotations

from app.report.models import DailyReportDocument, ReportItem


def render_markdown(doc: DailyReportDocument) -> str:
    lines = [
        f"# {doc.title}",
        "",
        f"**Date:** {doc.report_date.isoformat()}",
        "",
        _stats_line(doc),
        "",
        "## Executive Summary",
        "",
    ]
    if not doc.executive:
        lines.append("No ranked items were available for this cycle.")
        lines.append("")
    for index, item in enumerate(doc.executive, start=1):
        lines.append(f"{index}. **{item.title}** — {_one_line(item.why_it_matters or item.summary)}")
        lines.append(f"   Source: [{item.source_name}]({item.source_url})")
        lines.append("")

    lines.extend(["## Top AI Developments", ""])
    _section_items(lines, doc.developments, kind="story")

    lines.extend(["## Research Advancements", ""])
    _section_items(lines, doc.research, kind="research")

    lines.extend(["## Industry & Product Updates", ""])
    _section_items(lines, doc.industry, kind="industry")

    lines.extend(["## What to Watch", ""])
    if not doc.watch:
        lines.append("- Nothing flagged beyond the items above.")
    for trend in doc.watch:
        lines.append(f"- {trend}")
    lines.extend(["", "## Sources", ""])
    if not doc.sources:
        lines.append("No sources.")
    for name, url in doc.sources:
        lines.append(f"- [{name}]({url})")
    lines.append("")
    return "\n".join(lines)


def _section_items(lines: list[str], items: list[ReportItem], *, kind: str) -> None:
    if not items:
        lines.append("No items in this section.")
        lines.append("")
        return
    for item in items:
        lines.append(f"### {item.title}")
        lines.append("")
        if kind == "research":
            if item.problem:
                lines.append(f"**Problem:** {item.problem}")
            if item.key_contribution:
                lines.append(f"**Key contribution:** {item.key_contribution}")
        else:
            lines.append(item.summary)
        lines.append("")
        if item.why_it_matters:
            lines.append(f"**Why it matters:** {item.why_it_matters}")
            lines.append("")
        source_line = f"**Source:** [{item.source_name}]({item.source_url})"
        if item.published_at:
            source_line += f" — {item.published_at[:10]}"
        lines.append(source_line)
        if item.supporting_sources:
            lines.append("**Supporting sources:** " + "; ".join(item.supporting_sources))
        if item.insufficient_information or item.validation_flags:
            notes = ", ".join(item.validation_flags) or "insufficient source text"
            lines.append(f"*Validation notes:* {notes}")
        lines.append("")


def _stats_line(doc: DailyReportDocument) -> str:
    stats = doc.stats
    flagged = int(stats.get("flagged", 0) or 0)
    flag_bit = (
        "no source-check warnings"
        if flagged == 0
        else f"{flagged} source-check warning"
        if flagged == 1
        else f"{flagged} source-check warnings"
    )
    parts = [
        f"Scored items considered: {stats.get('candidates', 0)}",
        f"In this report: {stats.get('selected', 0)}",
        flag_bit,
    ]
    return "*" + " · ".join(parts) + "*"


def _one_line(text: str) -> str:
    return " ".join((text or "").split())
