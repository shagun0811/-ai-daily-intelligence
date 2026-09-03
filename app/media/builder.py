"""Build infographic, story cards, GIF, and a short briefing MP4 from the text report.

Uses Pillow for stills. MP4 needs local ffmpeg (GitHub Actions installs it).
If ffmpeg is missing the GIF still writes and the job does not fail.
No paid image/video APIs and no LLM.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from app.config.logging import STAGE_REPORT, get_logger, log_stage
from app.media.draw import ACCENT, BG, BAR_TRACK, GOLD, MUTED, PANEL, TEXT, TITLE, load_font, wrap_text
from app.media.video import build_slides, encode_mp4
from app.report.models import DailyReportDocument, ReportItem

logger = get_logger(__name__)

INFOGRAPHIC_SIZE = (1080, 1440)
CARD_SIZE = (1080, 1080)
VIDEO_SIZE = (720, 720)


@dataclass
class MediaBundle:
    infographic_path: str | None = None
    card_paths: list[str] = field(default_factory=list)
    video_path: str | None = None
    mp4_path: str | None = None
    slide_count: int = 0
    errors: list[str] = field(default_factory=list)

    def as_stats(self) -> dict:
        return {
            "infographic_path": self.infographic_path,
            "card_paths": self.card_paths,
            "video_path": self.video_path,
            "mp4_path": self.mp4_path,
            "slide_count": self.slide_count,
        }


def write_media_pack(document: DailyReportDocument, *, out_dir: Path, stem: str) -> MediaBundle:
    """Write infographic PNG, story-card PNGs, looping GIF, and MP4 when ffmpeg exists."""
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = MediaBundle()
    try:
        infographic_image = _render_infographic(document)
        infographic = out_dir / f"{stem}-infographic.png"
        infographic_image.save(infographic, "PNG")
        bundle.infographic_path = str(infographic)

        cards: list[Image.Image] = []
        for index, item in enumerate(document.executive[:5], start=1):
            image = _render_card(document, item, index=index)
            path = out_dir / f"{stem}-card-{index:02d}.png"
            image.save(path, "PNG")
            bundle.card_paths.append(str(path))
            cards.append(image)

        slides = build_slides(document, infographic_image=infographic_image)
        bundle.slide_count = len(slides)

        gif_frames = _gif_frames(document, infographic_image=infographic_image, cards=cards)
        video = out_dir / f"{stem}-briefing.gif"
        gif_frames[0].save(
            video,
            save_all=True,
            append_images=gif_frames[1:],
            duration=1800,
            loop=0,
            optimize=True,
        )
        bundle.video_path = str(video)

        mp4 = encode_mp4(slides, out_dir / f"{stem}-briefing.mp4", allow_download=True)
        if mp4 is not None:
            bundle.mp4_path = str(mp4)

        log_stage(
            logger,
            STAGE_REPORT,
            "media infographic=%s cards=%s gif=%s mp4=%s slides=%s",
            infographic.name,
            len(bundle.card_paths),
            video.name,
            Path(bundle.mp4_path).name if bundle.mp4_path else "-",
            bundle.slide_count,
        )
    except Exception as exc:  # noqa: BLE001
        bundle.errors.append(str(exc))
        log_stage(logger, STAGE_REPORT, "media write failed error=%s", exc, level=40)
    return bundle


def _render_infographic(document: DailyReportDocument) -> Image.Image:
    width, height = INFOGRAPHIC_SIZE
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    title_font = load_font(54)
    kicker_font = load_font(22)
    body_font = load_font(32)
    small_font = load_font(24)
    label_font = load_font(20)

    draw.rounded_rectangle((48, 48, width - 48, 220), radius=28, fill=PANEL)
    draw.text((80, 72), "DAILY BRIEFING", font=kicker_font, fill=ACCENT)
    draw.text((80, 112), "AI Daily Intelligence", font=title_font, fill=TITLE)
    draw.text((80, 176), document.report_date.isoformat(), font=small_font, fill=GOLD)

    stats = document.stats or {}
    selected = int(stats.get("selected") or len(_all_items(document)))
    sources = len(document.sources)
    draw.rounded_rectangle((48, 252, 516, 370), radius=22, fill=PANEL)
    draw.rounded_rectangle((564, 252, width - 48, 370), radius=22, fill=PANEL)
    draw.text((80, 272), str(selected), font=title_font, fill=ACCENT)
    draw.text((80, 332), "stories in today's pack", font=label_font, fill=MUTED)
    draw.text((596, 272), str(sources), font=title_font, fill=GOLD)
    draw.text((596, 332), "distinct sources", font=label_font, fill=MUTED)

    draw.text((80, 410), "Top stories", font=small_font, fill=ACCENT)
    y = 460
    for index, item in enumerate(document.executive[:5], start=1):
        lines = wrap_text(draw, item.title, body_font, width - 200, max_lines=2)
        draw.text((80, y), f"{index:02d}", font=body_font, fill=GOLD)
        for line in lines:
            draw.text((160, y), line, font=body_font, fill=TEXT)
            y += 40
        y += 18

    counts = _category_counts(document)
    draw.text((80, 1080), "Mix by category", font=small_font, fill=ACCENT)
    bar_y = 1140
    max_count = max(counts.values()) if counts else 1
    for name, count in list(counts.items())[:5]:
        draw.text((80, bar_y), name.replace("_", " ")[:22], font=label_font, fill=MUTED)
        track = (400, bar_y + 6, width - 80, bar_y + 28)
        draw.rounded_rectangle(track, radius=10, fill=BAR_TRACK)
        fill_w = 400 + int((width - 480) * (count / max_count))
        draw.rounded_rectangle((400, bar_y + 6, fill_w, bar_y + 28), radius=10, fill=ACCENT)
        bar_y += 48

    draw.text(
        (80, height - 70),
        "Local text pipeline · no paid image or video APIs",
        font=label_font,
        fill=MUTED,
    )
    return image


def _render_card(document: DailyReportDocument, item: ReportItem, *, index: int) -> Image.Image:
    width, height = CARD_SIZE
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    kicker_font = load_font(24)
    title_font = load_font(48)
    body_font = load_font(30)
    small_font = load_font(24)

    draw.rounded_rectangle((48, 48, width - 48, height - 48), radius=36, fill=PANEL)
    kind = (item.category or item.schema_name or "story").replace("_", " ").upper()
    draw.text((96, 88), f"{index:02d}  ·  {kind}", font=kicker_font, fill=ACCENT)
    draw.text((96, 130), document.report_date.isoformat(), font=small_font, fill=GOLD)

    title_lines = wrap_text(draw, item.title, title_font, width - 192, max_lines=5)
    y = 210
    for line in title_lines:
        draw.text((96, y), line, font=title_font, fill=TITLE)
        y += 58

    why = item.why_it_matters or item.summary or ""
    draw.text((96, y + 20), "Why it matters", font=kicker_font, fill=ACCENT)
    why_lines = wrap_text(draw, why, body_font, width - 192, max_lines=5)
    y = y + 60
    for line in why_lines:
        draw.text((96, y), line, font=body_font, fill=TEXT)
        y += 40

    draw.text((96, height - 140), item.source_name, font=small_font, fill=GOLD)
    draw.text((96, height - 100), "AI Daily Intelligence", font=kicker_font, fill=MUTED)
    return image


def _render_title_card(document: DailyReportDocument) -> Image.Image:
    image = Image.new("RGB", CARD_SIZE, BG)
    draw = ImageDraw.Draw(image)
    kicker = load_font(26)
    title = load_font(62)
    body = load_font(32)
    draw.text((90, 360), "AI DAILY INTELLIGENCE", font=kicker, fill=ACCENT)
    draw.text((90, 430), "Today in 60 seconds", font=title, fill=TITLE)
    draw.text((90, 530), document.report_date.isoformat(), font=body, fill=GOLD)
    draw.text((90, 620), f"{len(document.executive)} headline cards", font=body, fill=TEXT)
    return image


def _render_end_card() -> Image.Image:
    image = Image.new("RGB", CARD_SIZE, BG)
    draw = ImageDraw.Draw(image)
    title = load_font(52)
    body = load_font(28)
    draw.text((90, 430), "That's the briefing.", font=title, fill=TITLE)
    draw.text((90, 520), "Full sources are in the Markdown / PDF report.", font=body, fill=MUTED)
    return image


def _gif_frames(
    document: DailyReportDocument,
    *,
    infographic_image: Image.Image,
    cards: list[Image.Image],
) -> list[Image.Image]:
    frames = [_fit(_render_title_card(document), VIDEO_SIZE)]
    frames.append(_fit(infographic_image, VIDEO_SIZE))
    frames.extend(_fit(card, VIDEO_SIZE) for card in cards)
    frames.append(_fit(_render_end_card(), VIDEO_SIZE))
    return frames


def _fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    fitted = Image.new("RGB", size, BG)
    resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
    copy = image.copy()
    copy.thumbnail(size, resample)
    x = (size[0] - copy.width) // 2
    y = (size[1] - copy.height) // 2
    fitted.paste(copy, (x, y))
    return fitted.convert("P", palette=Image.ADAPTIVE, colors=64)


def _all_items(document: DailyReportDocument) -> list[ReportItem]:
    return list(document.executive) + list(document.developments) + list(document.research) + list(document.industry)


def _category_counts(document: DailyReportDocument) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in _all_items(document):
        counts[item.category or item.schema_name or "OTHER"] += 1
    return dict(counts.most_common())
