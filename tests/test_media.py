"""Visual briefing assets. Pillow only — no network and no paid APIs."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.media.builder import write_media_pack
from app.media.video import build_slides
from app.report.models import DailyReportDocument, ReportItem


def _item(title: str, **fields) -> ReportItem:
    return ReportItem(
        article_id=fields.pop("article_id", 1),
        title=title,
        summary=fields.pop("summary", "A short summary of the story."),
        why_it_matters=fields.pop("why_it_matters", "It changes how teams ship models."),
        source_name=fields.pop("source_name", "Google AI Blog"),
        source_url=fields.pop("source_url", "https://blog.google/example"),
        category=fields.pop("category", "MODEL_RELEASE"),
        schema_name=fields.pop("schema_name", "news"),
        **fields,
    )


def _sample_document() -> DailyReportDocument:
    return DailyReportDocument(
        report_date=date(2026, 8, 17),
        executive=[
            _item("Open-weights language model release", article_id=1),
            _item(
                "Retrieval method for agentic RAG",
                article_id=2,
                category="RESEARCH",
                schema_name="research",
                source_name="arXiv cs.AI",
                source_url="https://arxiv.org/abs/2608.1",
            ),
        ],
        research=[
            _item(
                "Retrieval method for agentic RAG",
                article_id=2,
                category="RESEARCH",
                schema_name="research",
            )
        ],
        sources=[("Google AI Blog", "https://blog.google/example")],
        stats={"selected": 2, "candidates": 8, "flagged": 0},
    )


def test_media_pack_writes_infographic_cards_and_gif(tmp_path: Path) -> None:
    bundle = write_media_pack(_sample_document(), out_dir=tmp_path, stem="ai-daily-intelligence-2026-08-17")
    assert not bundle.errors
    infographic = Path(bundle.infographic_path or "")
    video = Path(bundle.video_path or "")
    assert infographic.is_file()
    assert infographic.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(bundle.card_paths) == 2
    assert Path(bundle.card_paths[0]).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert video.is_file()
    assert video.read_bytes()[:6] in {b"GIF87a", b"GIF89a"}


def test_media_pack_writes_mp4_or_gif_with_slides(tmp_path: Path) -> None:
    document = _sample_document()
    slides = build_slides(document)
    assert len(slides) >= 4
    bundle = write_media_pack(document, out_dir=tmp_path, stem="ai-daily-intelligence-2026-08-17")
    assert not bundle.errors
    assert bundle.slide_count >= 4
    gif = Path(bundle.video_path or "")
    assert gif.is_file()
    assert gif.read_bytes()[:6] in {b"GIF87a", b"GIF89a"}
    if bundle.mp4_path:
        mp4 = Path(bundle.mp4_path)
        assert mp4.is_file()
        assert mp4.read_bytes()[4:8] == b"ftyp"


def test_empty_report_still_writes_infographic_and_video(tmp_path: Path) -> None:
    document = DailyReportDocument(report_date=date(2026, 8, 18), stats={"selected": 0, "candidates": 0})
    bundle = write_media_pack(document, out_dir=tmp_path, stem="empty-day")
    assert not bundle.errors
    assert Path(bundle.infographic_path or "").is_file()
    assert Path(bundle.video_path or "").is_file()
    assert bundle.card_paths == []
    assert bundle.slide_count >= 2
