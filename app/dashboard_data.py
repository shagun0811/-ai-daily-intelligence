"""Read-only queries for the Streamlit dashboard. Never scrapes or writes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database.models import Article, ArticleTopic, DailyReport, ItemScore, PipelineRun, Source
from app.database.repository import Repository
from app.report.ranker import latest_summary

_BRIEF_KEYS = (
    "what_happened",
    "why_it_matters",
    "key_innovation",
    "problem",
    "announcement",
    "interpretation",
)


def filter_options(session: Session) -> dict[str, list[str]]:
    sources = [name for name in session.scalars(select(Source.name).order_by(Source.name)) if name]
    categories = [
        value
        for value in session.scalars(
            select(Article.llm_category).where(Article.llm_category.is_not(None)).distinct()
        )
        if value
    ]
    statuses = [
        value
        for value in session.scalars(select(Article.processing_status).distinct())
        if value
    ]
    kinds = [value for value in session.scalars(select(Article.item_kind).distinct()) if value]
    return {
        "sources": sources,
        "categories": sorted(categories),
        "statuses": sorted(statuses),
        "kinds": sorted(kinds),
    }


def dashboard_stats(session: Session) -> dict[str, Any]:
    total = session.scalar(select(func.count(Article.id))) or 0
    scored = session.scalar(select(func.count(ItemScore.id))) or 0
    avg_score = session.scalar(select(func.avg(ItemScore.weighted_total)))
    reports = session.scalar(select(func.count(DailyReport.id))) or 0
    latest_report = session.scalar(select(func.max(DailyReport.report_date)))
    last_run = session.scalar(select(PipelineRun).order_by(PipelineRun.id.desc()))

    status_rows = session.execute(
        select(Article.processing_status, func.count(Article.id)).group_by(Article.processing_status)
    ).all()
    category_rows = session.execute(
        select(Article.llm_category, func.count(Article.id))
        .where(Article.llm_category.is_not(None))
        .group_by(Article.llm_category)
    ).all()
    kind_rows = session.execute(
        select(Article.item_kind, func.count(Article.id)).group_by(Article.item_kind)
    ).all()

    relevant = session.scalar(
        select(func.count(ItemScore.id)).where(
            func.json_extract(ItemScore.explanation_json, "$.relevant") == 1
        )
    ) or 0

    return {
        "articles": int(total),
        "scored": int(scored),
        "relevant": relevant,
        "average_score": round(float(avg_score), 2) if avg_score is not None else None,
        "reports": int(reports),
        "latest_report_date": latest_report.isoformat() if latest_report else None,
        "last_run_status": last_run.status if last_run else None,
        "last_run_stage": last_run.current_stage if last_run else None,
        "by_status": {str(name): int(count) for name, count in status_rows if name},
        "by_category": {str(name): int(count) for name, count in category_rows if name},
        "by_kind": {str(name): int(count) for name, count in kind_rows if name},
    }


def search_items(
    session: Session,
    *,
    query: str = "",
    source_name: str | None = None,
    category: str | None = None,
    status: str | None = None,
    item_kind: str | None = None,
    min_score: float | None = None,
    relevant_only: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    stmt = (
        select(Article)
        .options(
            selectinload(Article.source),
            selectinload(Article.score),
            selectinload(Article.topic_links).selectinload(ArticleTopic.topic),
            selectinload(Article.processing_results),
        )
        .outerjoin(ItemScore, ItemScore.article_id == Article.id)
        .outerjoin(Source, Source.id == Article.source_id)
    )
    needle = query.strip().lower()
    if needle:
        pattern = f"%{needle}%"
        stmt = stmt.where(
            or_(
                func.lower(Article.title).like(pattern),
                func.lower(Article.url).like(pattern),
                func.lower(func.coalesce(Article.cleaned_text, "")).like(pattern),
                func.lower(func.coalesce(Article.description, "")).like(pattern),
            )
        )
    if source_name:
        stmt = stmt.where(Source.name == source_name)
    if category:
        stmt = stmt.where(Article.llm_category == category)
    if status:
        stmt = stmt.where(Article.processing_status == status)
    if item_kind:
        stmt = stmt.where(Article.item_kind == item_kind)
    if min_score is not None:
        stmt = stmt.where(ItemScore.weighted_total >= min_score)
    stmt = stmt.order_by(ItemScore.weighted_total.desc().nullslast(), Article.id.desc()).limit(limit)
    rows = list(session.scalars(stmt).unique().all())
    items = [_item_row(article) for article in rows]
    if relevant_only:
        items = [item for item in items if item.get("relevant")]
    return items


def get_item_detail(session: Session, article_id: int) -> dict[str, Any] | None:
    article = Repository(session).get_article_by_id(article_id)
    if article is None:
        return None
    row = _item_row(article)
    summary = latest_summary(article) or {}
    score = article.score
    paper = article.research_paper
    row.update(
        {
            "summary": summary,
            "brief": _brief(summary),
            "score_components": {
                "recency": score.recency,
                "credibility": score.credibility,
                "relevance": score.relevance,
                "novelty": score.novelty,
                "technical_significance": score.technical_significance,
                "industry_impact": score.industry_impact,
                "research_significance": score.research_significance,
                "weighted_total": score.weighted_total,
            }
            if score is not None
            else {},
            "abstract": paper.abstract if paper is not None else None,
            "arxiv_id": paper.arxiv_id if paper is not None else None,
        }
    )
    return row


def list_reports(session: Session) -> list[dict[str, Any]]:
    reports = Repository(session).list_daily_reports()
    payload: list[dict[str, Any]] = []
    for report in reports:
        payload.append(
            {
                "id": report.id,
                "report_date": report.report_date.isoformat(),
                "title": report.title,
                "markdown_content": report.markdown_content,
                "markdown_path": report.markdown_path,
                "html_path": report.html_path,
                "pdf_path": report.pdf_path,
                "stats": report.stats_json or {},
                "files": _existing_files(report),
            }
        )
    return payload


def read_report_bytes(path: str | None) -> bytes | None:
    if not path:
        return None
    file_path = Path(path)
    if not file_path.is_file():
        return None
    return file_path.read_bytes()


def _existing_files(report: DailyReport) -> dict[str, Any]:
    files: dict[str, Any] = {}
    for label, path in (
        ("markdown", report.markdown_path),
        ("html", report.html_path),
        ("pdf", report.pdf_path),
    ):
        if path and Path(path).is_file():
            files[label] = path
    stats = report.stats_json or {}
    infographic = stats.get("infographic_path")
    video = stats.get("video_path")
    cards = [path for path in (stats.get("card_paths") or []) if path and Path(path).is_file()]
    if report.markdown_path:
        parent = Path(report.markdown_path).parent
        stem = Path(report.markdown_path).stem
        infographic = infographic or str(parent / f"{stem}-infographic.png")
        video = video or str(parent / f"{stem}-briefing.gif")
        if not cards:
            cards = [str(path) for path in sorted(parent.glob(f"{stem}-card-*.png"))]
    if infographic and Path(infographic).is_file():
        files["infographic"] = infographic
    if video and Path(video).is_file():
        files["video"] = video
    if cards:
        files["cards"] = cards
    return files


def _item_row(article: Article) -> dict[str, Any]:
    score = article.score
    explanation = (score.explanation_json if score is not None else None) or {}
    topics = []
    for link in article.topic_links:
        topic = getattr(link, "topic", None)
        if topic is not None and topic.name:
            topics.append(topic.name)
    return {
        "id": article.id,
        "title": article.title,
        "url": article.url,
        "source": getattr(article.source, "name", "") or "",
        "category": article.llm_category or "",
        "status": article.processing_status,
        "item_kind": article.item_kind,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "score": float(score.weighted_total) if score is not None else None,
        "relevant": bool(explanation.get("relevant")),
        "topics": topics,
        "brief": _brief(latest_summary(article) or {}),
    }


def _brief(summary: dict[str, Any]) -> str:
    for key in _BRIEF_KEYS:
        value = summary.get(key)
        if isinstance(value, str) and value.strip() and "not stated" not in value.lower():
            return " ".join(value.split())[:280]
    return ""
