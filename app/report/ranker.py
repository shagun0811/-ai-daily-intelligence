"""Pick a short, ranked set of items for the ~2-page report."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime
import unicodedata

from app.database.enums import ClusterMemberRole
from app.database.models import Article
from app.llm.prompts import schema_for
from app.report.models import DailyReportDocument, ReportItem
from app.report.validator import ValidationResult

HERO_MAX_AGE_DAYS = 4
REUSE_NEWS_MAX_AGE_DAYS = 2
PAPER_MAX_AGE_DAYS = 3
BRIEFING_MAX_AGE_DAYS = 7


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


def published_day(item: ReportItem) -> date | None:
    value = item.published_at
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def age_days(item: ReportItem, report_date: date | None) -> int | None:
    if report_date is None:
        return None
    published = published_day(item)
    if published is None:
        return None
    return (report_date - published).days


def ranking_score(item: ReportItem, report_date: date | None = None) -> float:
    """News and today's stories outrank leftover papers and old product posts."""
    score = float(item.score or 0.0)
    is_paper = item.schema_name == "research"
    if is_paper:
        score -= 1.8
    else:
        score += 1.25
    if report_date is None:
        return score
    age = age_days(item, report_date)
    if age is None:
        score -= 0.15
    elif age <= 0:
        score += 1.6
    elif age <= 1:
        score += 1.1
    elif age <= 2:
        score += 0.35
    elif age <= 4:
        score -= 0.9
    elif age <= 7:
        score -= 2.6
    else:
        score -= 8.0
    if is_paper and age is not None and age > 1:
        score -= 1.4
    return score


def mix_for_report(
    items: list[ReportItem],
    *,
    cap: int,
    max_research: int = 2,
    blocked_ids: set[int] | None = None,
    report_date: date | None = None,
) -> list[ReportItem]:
    """Fill the briefing with current news first; keep only a few fresh papers."""
    blocked = blocked_ids or set()
    ranked = sorted(items, key=lambda item: ranking_score(item, report_date), reverse=True)
    news = [item for item in ranked if item.schema_name != "research"]
    papers = [item for item in ranked if item.schema_name == "research"]

    news = [item for item in news if _within_age(item, report_date, BRIEFING_MAX_AGE_DAYS)]
    papers = [item for item in papers if _within_age(item, report_date, PAPER_MAX_AGE_DAYS)]

    unreported_news = [item for item in news if item.article_id not in blocked]
    reuse_news = [
        item
        for item in news
        if item.article_id in blocked and _reuse_news(item, report_date)
    ]
    selected_news = _dedupe_titles(unreported_news + reuse_news)
    unreported_papers = _dedupe_titles([item for item in papers if item.article_id not in blocked])
    if not selected_news and not unreported_papers:
        unreported_papers = [
            item
            for item in papers
            if item.article_id in blocked and _within_age(item, report_date, 1)
        ]

    news_floor = min(5, len(selected_news), cap)
    paper_take = min(len(unreported_papers), max_research, max(0, cap - news_floor))
    news_take = min(len(selected_news), max(0, cap - paper_take))
    selected = selected_news[:news_take] + unreported_papers[:paper_take]
    leftover = max(0, cap - len(selected))
    if leftover:
        selected.extend(selected_news[news_take : news_take + leftover])
    selected.sort(key=lambda item: ranking_score(item, report_date), reverse=True)
    return selected[:cap]


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
    max_research: int = 2,
    max_industry: int = 5,
    max_watch: int = 5,
    max_exec_papers: int = 0,
) -> DailyReportDocument:
    ranked = sorted(items, key=lambda item: ranking_score(item, report_date), reverse=True)
    others = [item for item in ranked if item.schema_name != "research"]
    papers = [item for item in ranked if item.schema_name == "research"]
    hero_pool = _dedupe_titles(
        [item for item in others if _within_age(item, report_date, HERO_MAX_AGE_DAYS)]
    )
    executive = hero_pool[:max_exec]
    if len(executive) < max_exec and max_exec_papers:
        executive.extend(papers[: min(max_exec_papers, max_exec - len(executive))])
    used = {item.article_id for item in executive}
    research = [item for item in papers if item.article_id not in used][:max_research]
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


def _dedupe_titles(items: list[ReportItem]) -> list[ReportItem]:
    selected: list[ReportItem] = []
    titles: list[str] = []
    for item in items:
        if _is_near_duplicate_title(item.title, titles):
            continue
        selected.append(item)
        titles.append(item.title)
    return selected


_GENERIC_TITLE_WORDS = {
    "openai",
    "google",
    "microsoft",
    "amazon",
    "meta",
    "anthropic",
    "nvidia",
    "intel",
    "apple",
    "deepmind",
}


def _is_near_duplicate_title(title: str, existing: list[str]) -> bool:
    words = _significant_words(title)
    for other in existing:
        shared = [word for word in _significant_words(other) if word in words]
        distinctive = [word for word in shared if word not in _GENERIC_TITLE_WORDS]
        if any(len(word) >= 8 for word in distinctive) or len(distinctive) >= 2:
            return True
    return False


def _significant_words(title: str) -> list[str]:
    folded = "".join(
        ch.lower() if ch.isalnum() else " "
        for ch in unicodedata.normalize("NFD", title)
        if unicodedata.category(ch) != "Mn"
    )
    return [word for word in folded.split() if len(word) > 4]


def _within_age(item: ReportItem, report_date: date | None, limit: int) -> bool:
    age = age_days(item, report_date)
    if age is None:
        return True
    return age <= limit


def _reuse_news(item: ReportItem, report_date: date | None) -> bool:
    """Yesterday's still-breaking news can fill a new day when RSS has nothing newer."""
    age = age_days(item, report_date)
    if age is None:
        return False
    return age <= REUSE_NEWS_MAX_AGE_DAYS


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
