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
from app.report.validator import extract_numbers, validate_item
from app.utils.hashing import content_hash


def _article(db_session, *, source_name: str, title: str, url: str, text: str, **fields):
    repo = Repository(db_session)
    source = repo.get_source_by_name(source_name)
    assert source is not None
    article = repo.create_article(
        source=source,
        title=title,
        url=url,
        cleaned_text=text,
        description=text,
        content_hash=content_hash(text, url),
        published_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
        **fields,
    )
    article.processing_status = ProcessingStatus.DEDUPLICATED.value
    db_session.flush()
    db_session.refresh(article)
    return article


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
        text="A large language model paper with transformer training results.",
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


def test_report_skips_stories_already_used_on_a_prior_day(db_session, tmp_path: Path) -> None:
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
    )
    IntelligenceProcessor(db_session).run()
    Summarizer(db_session, provider=MockProvider("qwen3:4b")).run()
    day2 = ReportGenerator(db_session).run(report_date=date(2026, 8, 17), output_dir=tmp_path)
    assert day2.selected >= 1
    assert day2.skipped_repeat >= 1
    markdown2 = Path(day2.markdown_path).read_text(encoding="utf-8")
    assert "https://arxiv.org/abs/2608.77777" in markdown2
    assert "https://blog.google/no-repeat-primary" not in markdown2
    assert "https://techcrunch.com/no-repeat-support" not in markdown2
    db_session.refresh(primary)
    db_session.refresh(later)
    assert primary.processing_status == ProcessingStatus.PUBLISHED.value
    assert later.processing_status == ProcessingStatus.PUBLISHED.value


def test_report_writes_empty_digest_when_all_stories_were_used(db_session, tmp_path: Path) -> None:
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
    empty = ReportGenerator(db_session).run(report_date=date(2026, 8, 17), output_dir=tmp_path)
    assert empty.selected == 0
    assert empty.skipped_repeat >= 1
    assert empty.markdown_path and Path(empty.markdown_path).exists()


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
