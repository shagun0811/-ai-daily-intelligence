"""Daily report tests. No network and no LLM beyond mock summaries."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.config.settings import clear_settings_cache
from app.database.enums import ClusterMemberRole, ProcessingStatus
from app.database.models import DailyReport
from app.database.repository import Repository
from app.llm.mock_provider import MockProvider
from app.processors.intelligence import IntelligenceProcessor
from app.processors.summarizer import Summarizer
from app.report.generator import ReportGenerator
from app.report.models import ReportItem
from app.report.ranker import build_document, mix_for_report
from app.report.validator import extract_numbers, validate_item
from app.utils.hashing import content_hash


def _article(db_session, *, source_name: str, title: str, url: str, text: str, **fields):
    repo = Repository(db_session)
    source = repo.get_source_by_name(source_name)
    assert source is not None
    fields = dict(fields)
    published_at = fields.pop("published_at", datetime(2026, 8, 16, tzinfo=timezone.utc))
    article = repo.create_article(
        source=source,
        title=title,
        url=url,
        cleaned_text=text,
        description=text,
        content_hash=content_hash(text, url),
        published_at=published_at,
        **fields,
    )
    article.processing_status = ProcessingStatus.DEDUPLICATED.value
    db_session.flush()
    db_session.refresh(article)
    return article


def _item(*, article_id: int, title: str, schema_name: str, score: float, published_at: str | None = None) -> ReportItem:
    return ReportItem(
        article_id=article_id,
        title=title,
        summary="summary",
        why_it_matters="why",
        source_name="Example",
        source_url=f"https://example.com/{article_id}",
        published_at=published_at,
        score=score,
        schema_name=schema_name,
    )


def test_mix_for_report_prefers_news_over_papers() -> None:
    papers = [
        _item(article_id=index, title=f"Paper {index}", schema_name="research", score=9.5 - index * 0.01)
        for index in range(1, 13)
    ]
    news = [
        _item(article_id=100, title="OpenAI launches GPT", schema_name="news", score=7.0),
        _item(article_id=101, title="Google model release", schema_name="company", score=6.8),
        _item(article_id=102, title="Startup funding round", schema_name="company", score=6.5),
    ]
    mixed = mix_for_report(papers + news, cap=8, max_research=2)
    schemas = [item.schema_name for item in mixed]
    titles = {item.title for item in mixed}
    assert schemas.count("research") == 2
    assert len(mixed) == 5
    assert "OpenAI launches GPT" in titles
    assert "Google model release" in titles
    assert "Startup funding round" in titles

    document = build_document(mixed, report_date=date(2026, 8, 18), stats={"selected": len(mixed)})
    assert sum(1 for item in document.executive if item.schema_name == "research") == 0
    assert len(document.research) <= 2


def test_fresh_news_is_reused_so_a_new_day_is_not_empty() -> None:
    news = _item(
        article_id=1,
        title="OpenAI chip results",
        schema_name="news",
        score=7.0,
        published_at="2026-08-26",
    )
    paper = _item(
        article_id=2,
        title="Niche Helmholtz resonator paper",
        schema_name="research",
        score=9.9,
        published_at="2026-08-27",
    )
    mixed = mix_for_report(
        [news, paper],
        cap=8,
        blocked_ids={1},
        report_date=date(2026, 8, 27),
    )
    titles = {item.title for item in mixed}
    assert "OpenAI chip results" in titles
    document = build_document(mixed, report_date=date(2026, 8, 27), stats={"selected": len(mixed)})
    assert document.executive
    assert document.executive[0].title == "OpenAI chip results"


def test_old_product_post_stays_out_of_hero() -> None:
    old = _item(
        article_id=1,
        title="August 10 product note",
        schema_name="company",
        score=9.4,
        published_at="2026-08-10",
    )
    fresh = _item(
        article_id=2,
        title="Today’s model launch",
        schema_name="news",
        score=6.2,
        published_at="2026-08-27",
    )
    five_day = _item(
        article_id=3,
        title="Five-day-old roundup",
        schema_name="news",
        score=8.8,
        published_at="2026-08-22",
    )
    mixed = mix_for_report([old, fresh, five_day], cap=8, report_date=date(2026, 8, 27))
    titles = {item.title for item in mixed}
    assert "Today’s model launch" in titles
    assert "August 10 product note" not in titles
    document = build_document(mixed, report_date=date(2026, 8, 27), stats={"selected": len(mixed)})
    executive_titles = [item.title for item in document.executive]
    assert executive_titles[0] == "Today’s model launch"
    assert "Five-day-old roundup" not in executive_titles
    assert "August 10 product note" not in executive_titles


def test_near_duplicate_headlines_do_not_fill_the_hero() -> None:
    items = [
        _item(article_id=1, title="Jalapeño’s first results show industry-leading speed", schema_name="company", score=8.8, published_at="2026-08-25"),
        _item(article_id=2, title="OpenAI says its Jalapeño chip can power faster AI responses", schema_name="news", score=8.6, published_at="2026-08-25"),
        _item(article_id=3, title="OpenAI subpoenaed by Alabama AG over Hugging Face hack", schema_name="news", score=7.4, published_at="2026-08-25"),
    ]
    mixed = mix_for_report(items, cap=8, report_date=date(2026, 8, 27))
    titles = [item.title for item in mixed]
    assert sum("Jalapeño" in title or "Jalapeno" in title for title in titles) == 1
    document = build_document(mixed, report_date=date(2026, 8, 27), stats={"selected": len(mixed)})
    assert any("Alabama" in item.title for item in document.executive)


def test_validator_flags_number_missing_from_source(db_session) -> None:
    article = _article(
        db_session,
        source_name="Google AI Blog",
        title="A language model update",
        url="https://blog.google/validate-numbers",
        text="Google released an open-weights language model.",
    )
    summary = {
        "what_happened": "Google released a model used by 98% of enterprises.",
        "who_is_involved": "Google",
        "what_is_new": "open-weights language model",
        "technical_significance": "open-weights",
        "industry_significance": "industry",
        "why_it_matters": "it matters",
        "facts": ["98% of enterprises"],
        "provenance": {
            "source_name": "Google AI Blog",
            "source_url": article.url,
            "published_at": "2026-08-16",
            "insufficient_information": False,
        },
    }
    result = validate_item(article, summary)
    assert any("98" in flag for flag in result.flags)
    assert result.ok is False
    assert extract_numbers(summary["what_happened"])
    assert "98%" not in extract_numbers(article.cleaned_text or "")


def test_validator_accepts_numbers_from_source(db_session) -> None:
    article = _article(
        db_session,
        source_name="Google AI Blog",
        title="A 7B language model",
        url="https://blog.google/validate-ok",
        text="Google released a 7B open-weights language model.",
    )
    summary = {
        "what_happened": "Google released a 7B open-weights language model.",
        "who_is_involved": "Google",
        "what_is_new": "7B open-weights",
        "technical_significance": "7B",
        "industry_significance": "open-weights",
        "why_it_matters": "open-weights release",
        "facts": ["7B open-weights language model"],
        "provenance": {
            "source_name": "Google AI Blog",
            "source_url": article.url,
            "published_at": "2026-08-16",
            "insufficient_information": False,
        },
    }
    result = validate_item(article, summary)
    assert result.ok is True
    assert not any(flag.startswith("number_not_in_source") for flag in result.flags)


def test_report_writes_md_html_pdf_and_skips_supporting(db_session, tmp_path: Path) -> None:
    primary = _article(
        db_session,
        source_name="Google AI Blog",
        title="Official large language model release with open weights",
        url="https://blog.google/report-primary",
        text="Google released an open-weights large language model checkpoint on Hugging Face.",
    )
    supporting = _article(
        db_session,
        source_name="TechCrunch AI",
        title="Official large language model release with open weights",
        url="https://techcrunch.com/report-support",
        text="Coverage of the open-weights large language model release.",
    )
    paper = _article(
        db_session,
        source_name="arXiv cs.AI / cs.LG / cs.CL",
        title="A retrieval method for agentic RAG systems",
        url="https://arxiv.org/abs/2608.33333",
        text="We propose a retrieval method for agentic RAG with transformer training results.",
        item_kind="research_paper",
    )
    repo = Repository(db_session)
    cluster = repo.create_story_cluster(
        event_title="LLM release",
        primary_article=primary,
        cluster_date=datetime.now(timezone.utc),
    )
    repo.add_cluster_member(cluster, primary, ClusterMemberRole.PRIMARY)
    repo.add_cluster_member(cluster, supporting, ClusterMemberRole.SUPPORTING)

    IntelligenceProcessor(db_session).run()
    Summarizer(db_session, provider=MockProvider("qwen3:4b")).run()
    result = ReportGenerator(db_session).run(report_date=date(2026, 8, 16), output_dir=tmp_path)

    assert result.selected >= 1
    assert result.markdown_path and Path(result.markdown_path).exists()
    markdown = Path(result.markdown_path).read_text(encoding="utf-8")
    html = Path(result.html_path).read_text(encoding="utf-8")
    pdf = Path(result.pdf_path).read_bytes()
    assert "# AI Daily Intelligence" in markdown
    assert "source-check" in markdown.lower()
    assert "https://blog.google/report-primary" in markdown
    assert 'href="https://blog.google/report-primary"' in html
    assert pdf.startswith(b"%PDF")
    assert result.infographic_path and Path(result.infographic_path).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert result.video_path and Path(result.video_path).read_bytes()[:6] in {b"GIF87a", b"GIF89a"}
    db_session.refresh(primary)
    db_session.refresh(supporting)
    db_session.refresh(paper)
    assert primary.processing_status == ProcessingStatus.PUBLISHED.value
    assert supporting.processing_status == ProcessingStatus.SCORED.value
    assert paper.processing_status == ProcessingStatus.PUBLISHED.value
    stored = db_session.scalar(select(DailyReport).where(DailyReport.report_date == date(2026, 8, 16)))
    assert stored is not None
    assert stored.pdf_path == result.pdf_path
    assert paper.id in (stored.stats_json or {}).get("article_ids", [])

    again = ReportGenerator(db_session).run(report_date=date(2026, 8, 16), output_dir=tmp_path)
    assert again.selected >= 1
    rows = list(db_session.scalars(select(DailyReport).where(DailyReport.report_date == date(2026, 8, 16))).all())
    assert len(rows) == 1


def test_report_respects_max_items(db_session, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REPORT_MAX_ITEMS", "1")
    clear_settings_cache()
    _article(
        db_session,
        source_name="arXiv cs.AI / cs.LG / cs.CL",
        title="Paper one on large language models",
        url="https://arxiv.org/abs/2608.44444",
        text="A large language model paper with transformer training results and inference benchmarks.",
        item_kind="research_paper",
    )
    _article(
        db_session,
        source_name="arXiv cs.AI / cs.LG / cs.CL",
        title="Paper two on retrieval augmented generation",
        url="https://arxiv.org/abs/2608.55555",
        text="A retrieval-augmented generation paper with agent benchmarks.",
        item_kind="research_paper",
    )
    IntelligenceProcessor(db_session).run()
    Summarizer(db_session, provider=MockProvider("qwen3:4b")).run()
    result = ReportGenerator(db_session).run(report_date=date(2026, 8, 17), output_dir=tmp_path)
    assert result.selected == 1
    clear_settings_cache()


def test_next_day_keeps_current_news_ahead_of_a_new_paper(db_session, tmp_path: Path) -> None:
    primary = _article(
        db_session,
        source_name="Google AI Blog",
        title="Official large language model release with open weights",
        url="https://blog.google/no-repeat-primary",
        text="Google released an open-weights large language model checkpoint on Hugging Face.",
    )
    supporting = _article(
        db_session,
        source_name="TechCrunch AI",
        title="Official large language model release with open weights",
        url="https://techcrunch.com/no-repeat-support",
        text="Coverage of the open-weights large language model release.",
    )
    repo = Repository(db_session)
    cluster = repo.create_story_cluster(
        event_title="LLM release no-repeat",
        primary_article=primary,
        cluster_date=datetime.now(timezone.utc),
    )
    repo.add_cluster_member(cluster, primary, ClusterMemberRole.PRIMARY)
    repo.add_cluster_member(cluster, supporting, ClusterMemberRole.SUPPORTING)

    IntelligenceProcessor(db_session).run()
    Summarizer(db_session, provider=MockProvider("qwen3:4b")).run()
    day1 = ReportGenerator(db_session).run(report_date=date(2026, 8, 16), output_dir=tmp_path)
    assert day1.selected >= 1
    markdown1 = Path(day1.markdown_path).read_text(encoding="utf-8")
    assert "https://blog.google/no-repeat-primary" in markdown1

    later = _article(
        db_session,
        source_name="arXiv cs.AI / cs.LG / cs.CL",
        title="A retrieval method for agentic RAG systems",
        url="https://arxiv.org/abs/2608.77777",
        text="We propose a retrieval method for agentic RAG with transformer training results.",
        item_kind="research_paper",
        published_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
    )
    IntelligenceProcessor(db_session).run()
    Summarizer(db_session, provider=MockProvider("qwen3:4b")).run()
    day2 = ReportGenerator(db_session).run(report_date=date(2026, 8, 17), output_dir=tmp_path)
    assert day2.selected >= 1
    markdown2 = Path(day2.markdown_path).read_text(encoding="utf-8")
    assert "https://blog.google/no-repeat-primary" in markdown2
    assert "https://arxiv.org/abs/2608.77777" in markdown2
    assert "https://techcrunch.com/no-repeat-support" not in markdown2
    db_session.refresh(primary)
    db_session.refresh(later)
    assert primary.processing_status == ProcessingStatus.PUBLISHED.value
    assert later.processing_status == ProcessingStatus.PUBLISHED.value


def test_new_day_reuses_still_fresh_rss_stories(db_session, tmp_path: Path) -> None:
    _article(
        db_session,
        source_name="arXiv cs.AI / cs.LG / cs.CL",
        title="A retrieval method for agentic RAG systems",
        url="https://arxiv.org/abs/2608.88888",
        text="We propose a retrieval method for agentic RAG with transformer training results.",
        item_kind="research_paper",
    )
    IntelligenceProcessor(db_session).run()
    Summarizer(db_session, provider=MockProvider("qwen3:4b")).run()
    first = ReportGenerator(db_session).run(report_date=date(2026, 8, 16), output_dir=tmp_path)
    assert first.selected >= 1
    again = ReportGenerator(db_session).run(report_date=date(2026, 8, 17), output_dir=tmp_path)
    assert again.selected >= 1
    assert again.markdown_path and Path(again.markdown_path).exists()
    markdown = Path(again.markdown_path).read_text(encoding="utf-8")
    assert "https://arxiv.org/abs/2608.88888" in markdown


def test_stale_reported_story_is_not_repeated(db_session, tmp_path: Path) -> None:
    old = _article(
        db_session,
        source_name="Google AI Blog",
        title="Official large language model release with open weights",
        url="https://blog.google/stale-primary",
        text="Google released an open-weights large language model checkpoint on Hugging Face.",
        published_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
    )
    IntelligenceProcessor(db_session).run()
    Summarizer(db_session, provider=MockProvider("qwen3:4b")).run()
    first = ReportGenerator(db_session).run(report_date=date(2026, 8, 10), output_dir=tmp_path)
    assert first.selected >= 1
    later = _article(
        db_session,
        source_name="TechCrunch AI",
        title="OpenAI announces a new model release with open weights",
        url="https://techcrunch.com/fresh-model",
        text="OpenAI released an open-weights large language model checkpoint. Weights available on Hugging Face for enterprise customers.",
        published_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
    )
    IntelligenceProcessor(db_session).run()
    Summarizer(db_session, provider=MockProvider("qwen3:4b")).run()
    day2 = ReportGenerator(db_session).run(report_date=date(2026, 8, 27), output_dir=tmp_path)
    assert day2.selected >= 1
    markdown = Path(day2.markdown_path).read_text(encoding="utf-8")
    assert "https://techcrunch.com/fresh-model" in markdown
    assert "https://blog.google/stale-primary" not in markdown
    db_session.refresh(old)
    db_session.refresh(later)
    assert later.processing_status == ProcessingStatus.PUBLISHED.value


def test_previously_reported_ids_backfill_published_when_stats_lack_ids(db_session) -> None:
    article = _article(
        db_session,
        source_name="Google AI Blog",
        title="Open weights large language model",
        url="https://blog.google/backfill-ids",
        text="Google released an open-weights large language model.",
    )
    article.processing_status = ProcessingStatus.PUBLISHED.value
    db_session.add(
        DailyReport(
            report_date=date(2026, 8, 16),
            title="AI Daily Intelligence",
            markdown_content="# old",
            stats_json={"selected": 1},
        )
    )
    db_session.flush()
    used = Repository(db_session).previously_reported_article_ids(before_date=date(2026, 8, 17))
    assert article.id in used
