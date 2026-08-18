"""Pick a short, ranked set of items for the ~2-page report."""

from __future__ import annotations

from collections import Counter

from app.database.enums import ClusterMemberRole
from app.database.models import Article
from app.llm.prompts import schema_for
from app.report.models import DailyReportDocument, ReportItem
from app.report.validator import ValidationResult


def latest_summary(article: Article) -> dict | None:
    results = [
        row
        for row in article.processing_results
        if row.stage == "SUMMARIZE" and row.output_json
    ]
    if not results:
        return None
    results.sort(key=lambda row: row.id, reverse=True)
    return dict(results[0].output_json)


def is_supporting(article: Article) -> bool:
    return any(link.role == ClusterMemberRole.SUPPORTING.value for link in article.cluster_memberships)


def supporting_labels(article: Article) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for membership in article.cluster_memberships:
        cluster = membership.cluster
        if cluster is None:
            continue
        for mate in cluster.members:
            if mate.article_id == article.id:
                continue
            other = mate.article
            name = getattr(getattr(other, "source", None), "name", None) or "supporting source"
            url = getattr(other, "url", "") or ""
            key = f"{name}|{url}"
            if key in seen:
                continue
            seen.add(key)
            labels.append(f"{name} ({url})" if url else name)
    return labels


def to_report_item(article: Article, summary: dict, validation: ValidationResult) -> ReportItem:
    kind = schema_for(article)
    score = float(article.score.weighted_total) if article.score is not None else 0.0
    return ReportItem(
        article_id=article.id,
        title=article.title,
        summary=_summary_text(summary, kind),
        why_it_matters=_why(summary),
        problem=str(summary.get("problem") or ""),
        key_contribution=str(summary.get("key_innovation") or summary.get("key_contribution") or ""),
        source_name=validation.provenance_source_name,
        source_url=validation.provenance_source_url or article.url,
        published_at=validation.provenance_published_at,
        supporting_sources=supporting_labels(article),
        score=score,
        category=article.llm_category or "OTHER",
        schema_name=kind,
        validation_flags=list(validation.flags),
        insufficient_information=validation.insufficient_information,
    )


def build_document(
    items: list[ReportItem],
    *,
    report_date,
    stats: dict,
    max_exec: int = 5,
    max_dev: int = 8,
    max_research: int = 5,
    max_industry: int = 5,
    max_watch: int = 5,
) -> DailyReportDocument:
    ranked = sorted(items, key=lambda item: item.score, reverse=True)
    executive = ranked[:max_exec]
    used = {item.article_id for item in executive}
    research = [item for item in ranked if item.schema_name == "research" and item.article_id not in used][:max_research]
    used.update(item.article_id for item in research)
    industry = [item for item in ranked if item.schema_name == "company" and item.article_id not in used][:max_industry]
    used.update(item.article_id for item in industry)
    developments = [item for item in ranked if item.article_id not in used][:max_dev]

    sources: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in executive + developments + research + industry:
        if item.source_url in seen:
            continue
        seen.add(item.source_url)
        sources.append((item.source_name, item.source_url))

    return DailyReportDocument(
        report_date=report_date,
        executive=executive,
        developments=developments,
        research=research,
        industry=industry,
        watch=_watch(ranked, max_watch),
        sources=sources,
        stats=stats,
    )


def _summary_text(summary: dict, kind: str) -> str:
    if kind == "research":
        parts = [summary.get("problem"), summary.get("key_innovation"), summary.get("results")]
    elif kind == "company":
        parts = [summary.get("announcement"), summary.get("capabilities"), summary.get("availability")]
    else:
        parts = [summary.get("what_happened"), summary.get("what_is_new"), summary.get("who_is_involved")]
    text = " ".join(str(part).strip() for part in parts if part)
    return _clip(text, 700)


def _why(summary: dict) -> str:
    return _clip(
        str(summary.get("why_it_matters") or summary.get("business_significance") or summary.get("research_significance") or ""),
        400,
    )


def _clip(text: str, limit: int) -> str:
    body = " ".join((text or "").split())
    if len(body) <= limit:
        return body
    return body[: limit - 1].rstrip() + "…"


def _watch(items: list[ReportItem], limit: int) -> list[str]:
    counts: Counter[str] = Counter()
    for item in items:
        if item.insufficient_information:
            counts["Thin source text — fuller coverage may appear later"] += 1
        if item.schema_name == "research":
            counts["New research papers on the selected topics"] += 1
        elif item.schema_name == "company":
            counts["Model and product announcements"] += 1
        else:
            counts["Industry news follow-through"] += 1
        if item.category and item.category != "OTHER":
            counts[f"Category {item.category.replace('_', ' ').title()}"] += 1
    if not counts:
        return ["No high-confidence items were available for this cycle."]
    return [name for name, _count in counts.most_common(limit)]
