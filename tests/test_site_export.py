"""Static Cloudflare site export tests. No network."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from app.config.settings import PROJECT_ROOT
from app.database.enums import ProcessingStatus
from app.database.models import DailyReport
from app.database.repository import Repository
from app.site_export import export_public_site
from app.utils.hashing import content_hash


def test_export_writes_json_and_copies_report_files(db_session, tmp_path: Path) -> None:
    repo = Repository(db_session)
    source = repo.get_source_by_name("Google AI Blog")
    assert source is not None
    article = repo.create_article(
        source=source,
        title="Open weights language model",
        url="https://blog.google/cloudflare-export",
        cleaned_text="Google released an open-weights language model.",
        description="Google released an open-weights language model.",
        content_hash=content_hash("body", "https://blog.google/cloudflare-export"),
        published_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
        llm_category="MODEL_RELEASE",
    )
    article.processing_status = ProcessingStatus.PUBLISHED.value
    db_session.flush()
    md = tmp_path / "ai-daily-intelligence-2026-08-17.md"
    md.write_text("# AI Daily Intelligence\n", encoding="utf-8")
    png = tmp_path / "ai-daily-intelligence-2026-08-17-infographic.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 16)
    db_session.add(
        DailyReport(
            report_date=date(2026, 8, 17),
            title="AI Daily Intelligence",
            markdown_content="# AI Daily Intelligence\n",
            markdown_path=str(md),
            stats_json={"selected": 1, "candidates": 4, "infographic_path": str(png)},
        )
    )
    db_session.flush()

    out = tmp_path / "site"
    summary = export_public_site(db_session, site_dir=out)
    assert not summary.errors
    payload = json.loads((out / "data" / "dashboard.json").read_text(encoding="utf-8"))
    assert payload["stats"]["articles"] >= 1
    assert any(item["id"] == article.id for item in payload["items"])
    assert payload["reports"][0]["files"]["markdown"].endswith(".md")
    assert (out / payload["reports"][0]["files"]["markdown"]).is_file()
    assert payload["reports"][0]["files"]["infographic"].endswith(".png")
    assert payload["reports"][0]["files"]["zip"].endswith("ai-daily-intelligence-2026-08-17.zip")
    zip_path = out / payload["reports"][0]["files"]["zip"]
    assert zip_path.is_file()
    history = json.loads((out / "data" / "history.json").read_text(encoding="utf-8"))
    assert history["count"] == 1
    assert history["dates"] == ["2026-08-17"]
    assert history["archive_start"] == "2026-08-17"
    assert payload["today"]
    assert payload["reports"][0]["briefing"]["title"] == "AI Daily Intelligence"


def _write_report(db_session, tmp_path: Path, day: date, title: str) -> Path:
    md = tmp_path / f"ai-daily-intelligence-{day.isoformat()}.md"
    md.write_text(f"# {title}\n", encoding="utf-8")
    db_session.add(
        DailyReport(
            report_date=day,
            title=title,
            markdown_content=f"# {title}\n",
            markdown_path=str(md),
            stats_json={"selected": 1, "candidates": 3},
        )
    )
    db_session.flush()
    return md


def test_export_keeps_every_daily_report_from_archive_start(db_session, tmp_path: Path) -> None:
    _write_report(db_session, tmp_path, date(2026, 8, 16), "AI Daily Intelligence 16")
    _write_report(db_session, tmp_path, date(2026, 8, 17), "AI Daily Intelligence 17")
    _write_report(db_session, tmp_path, date(2026, 8, 18), "AI Daily Intelligence 18")

    out = tmp_path / "site"
    summary = export_public_site(db_session, site_dir=out)
    assert not summary.errors
    payload = json.loads((out / "data" / "dashboard.json").read_text(encoding="utf-8"))
    dates = [row["report_date"] for row in payload["reports"]]
    assert dates == ["2026-08-18", "2026-08-17"]
    assert (out / "files" / "2026-08-17" / "ai-daily-intelligence-2026-08-17.md").is_file()
    assert (out / "files" / "2026-08-18" / "ai-daily-intelligence-2026-08-18.md").is_file()
    assert (out / "files" / "2026-08-17" / "ai-daily-intelligence-2026-08-17.zip").is_file()
    assert not (out / "files" / "2026-08-16").exists()


def test_export_does_not_wipe_later_site_files(db_session, tmp_path: Path) -> None:
    _write_report(db_session, tmp_path, date(2026, 8, 17), "AI Daily Intelligence 17")
    out = tmp_path / "site"
    first = export_public_site(db_session, site_dir=out)
    assert not first.errors

    archived = out / "files" / "2026-08-18"
    archived.mkdir(parents=True)
    (archived / "ai-daily-intelligence-2026-08-18.md").write_text("# later briefing\n", encoding="utf-8")

    second = export_public_site(db_session, site_dir=out)
    assert not second.errors
    payload = json.loads((out / "data" / "dashboard.json").read_text(encoding="utf-8"))
    dates = [row["report_date"] for row in payload["reports"]]
    assert dates == ["2026-08-18", "2026-08-17"]
    assert (out / "files" / "2026-08-18" / "ai-daily-intelligence-2026-08-18.md").is_file()
    assert (out / "files" / "2026-08-17" / "ai-daily-intelligence-2026-08-17.md").is_file()
    assert (out / "files" / "2026-08-18" / "ai-daily-intelligence-2026-08-18.zip").is_file()


_SAMPLE_MARKDOWN = """# AI Daily Intelligence

**Date:** 2026-08-26

*Scored items considered: 12 · In this report: 2 · no source-check warnings*

## Executive Summary

1. **Jalapeño’s first results** — Custom inference chip with lower latency.
   Source: [OpenAI News](https://openai.com/index/jalapeno-first-results)

2. **OpenAI subpoenaed by Alabama AG** — Investigation after a Hugging Face hack.
   Source: [The Verge AI](https://www.theverge.com/example)

## Top AI Developments

### Recursive memory for long-horizon agents

Agents lose the task state as histories grow.

**Why it matters:** Long-horizon agents need working memory, not the full transcript.

**Source:** [arXiv cs.AI](https://arxiv.org/abs/2608.1) — 2026-08-25

## Research Advancements

No items in this section.

## What to Watch

- Chip benchmarks
- Safety investigations

## Sources

- [OpenAI News](https://openai.com/index/jalapeno-first-results)
- [The Verge AI](https://www.theverge.com/example)
"""


def test_parse_briefing_extracts_readable_day_report() -> None:
    from app.site_export import parse_briefing

    briefing = parse_briefing(_SAMPLE_MARKDOWN)
    assert briefing["title"] == "AI Daily Intelligence"
    assert briefing["date"] == "2026-08-26"
    assert "Jalapeño" in briefing["lede"]
    assert briefing["lede"].count("Jalapeño") == 1
    assert "subpoenaed" in briefing["lede"].lower()
    assert briefing["executive"][0]["title"] == "Jalapeño’s first results"
    assert briefing["executive"][0]["source_url"].endswith("jalapeno-first-results")
    assert briefing["sections"][0]["heading"] == "Top AI Developments"
    assert briefing["sections"][0]["items"][0]["title"].startswith("Recursive memory")
    assert "working memory" in briefing["sections"][0]["items"][0]["why_it_matters"]
    assert briefing["watch"] == ["Chip benchmarks", "Safety investigations"]
    assert briefing["sources"][0]["name"] == "OpenAI News"


def test_lede_skips_near_duplicate_headlines() -> None:
    from app.site_export import _lede_from_executive

    lede = _lede_from_executive(
        [
            {"title": "Jalapeño’s first results show industry-leading speed and efficiency in AI inference"},
            {"title": "OpenAI says its Jalapeño chip can power faster AI responses than the competition"},
            {"title": "OpenAI subpoenaed by Alabama AG over Hugging Face hack"},
            {"title": "Welcome to the AI crisis in math"},
        ]
    )
    assert "Jalapeño" in lede
    assert lede.lower().count("jalapeño") == 1
    assert "subpoenaed" in lede.lower()
    assert "math" in lede.lower()
    assert not lede.rstrip().endswith("and")


def test_export_hydrates_briefing_from_on_disk_markdown(db_session, tmp_path: Path) -> None:
    out = tmp_path / "site"
    folder = out / "files" / "2026-08-26"
    folder.mkdir(parents=True)
    (folder / "ai-daily-intelligence-2026-08-26.md").write_text(_SAMPLE_MARKDOWN, encoding="utf-8")

    summary = export_public_site(db_session, site_dir=out)
    assert not summary.errors
    payload = json.loads((out / "data" / "dashboard.json").read_text(encoding="utf-8"))
    dates = [row["report_date"] for row in payload["reports"]]
    assert "2026-08-26" in dates
    briefing = next(row["briefing"] for row in payload["reports"] if row["report_date"] == "2026-08-26")
    assert briefing["executive"][0]["title"] == "Jalapeño’s first results"
    assert briefing["sections"][0]["items"][0]["why_it_matters"]


def test_archive_page_is_a_day_reader() -> None:
    html = (PROJECT_ROOT / "site" / "index.html").read_text(encoding="utf-8")
    js = (PROJECT_ROOT / "site" / "briefing-20260826.js").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "site" / "briefing-20260826.css").read_text(encoding="utf-8")
    assert 'href="./briefing-20260826.css"' in html
    assert 'src="./briefing-20260826.js"' in html
    assert 'id="briefing"' in html
    assert 'id="date-strip"' in html
    assert 'id="prev-day"' in html
    assert 'id="next-day"' in html
    assert 'id="open-archive"' in html
    assert "Browse items" not in html
    assert "Cloudflare" not in html
    assert "static site" not in html.lower()
    assert "function renderBriefing" in js
    assert "function layoutBriefing" in js
    assert "Save this briefing" in js
    assert "Download all" in js
    assert "hero-card" in css
    assert "date-strip" in css


def test_paid_reader_opens_today_not_item_dump() -> None:
    html = (PROJECT_ROOT / "site" / "index.html").read_text(encoding="utf-8")
    js = (PROJECT_ROOT / "site" / "briefing-20260826.js").read_text(encoding="utf-8")
    assert 'id="item-list"' not in html
    assert 'data-tab="items"' not in html
    assert "Today in AI" in html
    assert "Archive" in html
    assert "local text pipeline" not in js.lower()
    assert "wrangler" not in js.lower()
    assert "python scripts/" not in js.lower()

