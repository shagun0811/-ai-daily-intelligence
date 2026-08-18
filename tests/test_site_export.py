"""Static Cloudflare site export tests. No network."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

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
