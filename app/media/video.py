"""Encode a short news-briefing MP4 from Pillow slides.

Uses local ffmpeg when it is on PATH (GitHub Actions installs it). If ffmpeg is
missing, the caller keeps the GIF fallback — this module never raises for that.
No paid video APIs and no TTS.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlopen

from PIL import Image, ImageDraw

from app.config.logging import STAGE_REPORT, get_logger, log_stage
from app.config.settings import PROJECT_ROOT
from app.media.draw import ACCENT, BG, GOLD, MUTED, PANEL, TEXT, TITLE, load_font, wrap_text
from app.report.models import DailyReportDocument, ReportItem

logger = get_logger(__name__)

SLIDE_SIZE = (1280, 720)
TITLE_MS = 3500
STORY_MS = 5500
INFOGRAPHIC_MS = 4000
END_MS = 3500
MAX_STORIES = 5
PUBLIC_SITE = "ai-daily-intelligence.pages.dev"

_CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "ffmpeg"
_WIN_FFMPEG_ZIPS = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
)


def build_slides(
    document: DailyReportDocument,
    *,
    infographic_image: Image.Image | None = None,
) -> list[tuple[Image.Image, int]]:
    """Title → 3–5 story slides → optional infographic → end card."""
    slides: list[tuple[Image.Image, int]] = [(_render_title_slide(document), TITLE_MS)]
    stories = list(document.executive[:MAX_STORIES])
    for index, item in enumerate(stories, start=1):
        slides.append((_render_story_slide(document, item, index=index), STORY_MS))
    if infographic_image is not None:
        slides.append((_fit_rgb(infographic_image, SLIDE_SIZE), INFOGRAPHIC_MS))
    slides.append((_render_end_slide(document), END_MS))
    return slides


def encode_mp4(
    slides: list[tuple[Image.Image, int]],
    dest: Path,
    *,
    allow_download: bool | None = None,
) -> Path | None:
    """Write dest as H.264 MP4. Returns the path, or None if ffmpeg is unavailable."""
    if not slides:
        return None
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if allow_download is None:
        allow_download = _env_flag("ADI_FETCH_FFMPEG")
    ffmpeg = find_ffmpeg(allow_download=allow_download)
    if not ffmpeg:
        log_stage(logger, STAGE_REPORT, "mp4 skipped: ffmpeg not found (GIF fallback stays)")
        return None
    with tempfile.TemporaryDirectory(prefix="adi-mp4-") as raw:
        tmp = Path(raw)
        concat = tmp / "slides.txt"
        lines: list[str] = []
        last_name = ""
        for index, (image, duration_ms) in enumerate(slides):
            name = f"slide-{index:02d}.png"
            _fit_rgb(image, SLIDE_SIZE).save(tmp / name, "PNG")
            seconds = max(0.5, duration_ms / 1000)
            lines.append(f"file '{name}'")
            lines.append(f"duration {seconds:.3f}")
            last_name = name
        lines.append(f"file '{last_name}'")
        concat.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if _run_ffmpeg(ffmpeg, concat, dest):
            log_stage(logger, STAGE_REPORT, "mp4 wrote %s slides=%s", dest.name, len(slides))
            return dest
    return None


def find_ffmpeg(*, allow_download: bool = False) -> str | None:
    env = (os.environ.get("FFMPEG_PATH") or "").strip()
    if env and Path(env).is_file():
        return env
    which = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if which:
        return which
    cached = _cached_ffmpeg()
    if cached:
        return str(cached)
    bundled = _imageio_ffmpeg()
    if bundled:
        return bundled
    if allow_download:
        downloaded = _download_ffmpeg()
        if downloaded:
            return str(downloaded)
    return None


def _env_flag(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _cached_ffmpeg() -> Path | None:
    names = ("ffmpeg.exe", "ffmpeg")
    for name in names:
        path = _CACHE_DIR / name
        if path.is_file():
            return path
    if _CACHE_DIR.is_dir():
        for path in _CACHE_DIR.rglob("ffmpeg.exe"):
            return path
        for path in _CACHE_DIR.rglob("ffmpeg"):
            if path.is_file() and os.access(path, os.X_OK):
                return path
    return None


def _imageio_ffmpeg() -> str | None:
    try:
        import imageio_ffmpeg
    except ImportError:
        return None
    try:
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None
    return exe if exe and Path(exe).is_file() else None


def _download_ffmpeg() -> Path | None:
    """Fetch a portable ffmpeg into data/cache. Windows zip; skip on other OS (apt)."""
    if os.name != "nt":
        return None
    cached = _cached_ffmpeg()
    if cached:
        return cached
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = _CACHE_DIR / "ffmpeg-essentials.zip"
    for url in _WIN_FFMPEG_ZIPS:
        try:
            log_stage(logger, STAGE_REPORT, "downloading portable ffmpeg")
            with urlopen(url, timeout=60) as response:  # noqa: S310
                with zip_path.open("wb") as handle:
                    while True:
                        chunk = response.read(1024 * 256)
                        if not chunk:
                            break
                        handle.write(chunk)
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(_CACHE_DIR)
            found = _cached_ffmpeg()
            if found:
                return found
        except Exception as exc:  # noqa: BLE001
            log_stage(logger, STAGE_REPORT, "ffmpeg download failed error=%s", exc, level=30)
    return None


def _run_ffmpeg(ffmpeg: str, concat: Path, dest: Path) -> bool:
    recipes = (
        ["-c:v", "libx264", "-profile:v", "baseline", "-level", "3.1", "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
        ["-c:v", "h264_mf", "-pix_fmt", "yuv420p"],
        ["-c:v", "mpeg4", "-q:v", "5"],
    )
    for extra in recipes:
        command = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat),
            *extra,
            "-an",
            str(dest),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=str(concat.parent),
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            log_stage(logger, STAGE_REPORT, "ffmpeg spawn failed error=%s", exc, level=30)
            return False
        if completed.returncode == 0 and dest.is_file() and dest.stat().st_size > 32:
            return True
        log_stage(
            logger,
            STAGE_REPORT,
            "ffmpeg encoder %s failed code=%s",
            extra[1],
            completed.returncode,
            level=30,
        )
    return False


def _render_title_slide(document: DailyReportDocument) -> Image.Image:
    width, height = SLIDE_SIZE
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((48, 48, width - 48, height - 48), radius=32, fill=PANEL)
    kicker = load_font(26)
    title = load_font(58)
    body = load_font(30)
    small = load_font(24)
    draw.text((96, 160), "DAILY BRIEFING", font=kicker, fill=ACCENT)
    draw.text((96, 220), "AI Daily Intelligence", font=title, fill=TITLE)
    draw.text((96, 310), document.report_date.isoformat(), font=body, fill=GOLD)
    n = len(document.executive[:MAX_STORIES])
    seconds = 8 + n * 6
    label = f"{n} top stor{'y' if n == 1 else 'ies'} · about {seconds} seconds" if n else "Today's briefing"
    draw.text((96, 390), label, font=body, fill=TEXT)
    draw.text((96, height - 140), PUBLIC_SITE, font=small, fill=GOLD)
    draw.text((96, height - 100), "Local slides · no paid video API · no voiceover", font=small, fill=MUTED)
    return image


def _render_story_slide(document: DailyReportDocument, item: ReportItem, *, index: int) -> Image.Image:
    width, height = SLIDE_SIZE
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((48, 48, width - 48, height - 48), radius=32, fill=PANEL)
    kicker = load_font(22)
    title = load_font(40)
    body = load_font(26)
    small = load_font(22)
    kind = (item.category or item.schema_name or "story").replace("_", " ").upper()
    draw.text((96, 80), f"{index:02d}  ·  {kind}", font=kicker, fill=ACCENT)
    draw.text((96, 118), document.report_date.isoformat(), font=small, fill=GOLD)

    title_lines = wrap_text(draw, item.title, title, width - 192, max_lines=3)
    y = 180
    for line in title_lines:
        draw.text((96, y), line, font=title, fill=TITLE)
        y += 50

    why = item.why_it_matters or item.summary or ""
    draw.text((96, y + 16), "Why it matters", font=kicker, fill=ACCENT)
    y += 52
    for line in wrap_text(draw, why, body, width - 192, max_lines=4):
        draw.text((96, y), line, font=body, fill=TEXT)
        y += 36

    draw.text((96, height - 120), item.source_name or "", font=small, fill=GOLD)
    draw.text((96, height - 86), "AI Daily Intelligence", font=kicker, fill=MUTED)
    return image


def _render_end_slide(document: DailyReportDocument) -> Image.Image:
    width, height = SLIDE_SIZE
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((48, 48, width - 48, height - 48), radius=32, fill=PANEL)
    title = load_font(48)
    body = load_font(26)
    small = load_font(24)
    draw.text((96, 210), "That's the briefing.", font=title, fill=TITLE)
    draw.text((96, 290), "Headlines and why they matter.", font=body, fill=TEXT)
    draw.text((96, 340), "Sources, ranks, and the PDF live on the site.", font=body, fill=TEXT)
    draw.text((96, 430), PUBLIC_SITE, font=body, fill=GOLD)
    draw.text((96, 490), document.report_date.isoformat(), font=small, fill=MUTED)
    draw.text((96, height - 120), "AI Daily Intelligence", font=small, fill=ACCENT)
    return image


def _fit_rgb(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    fitted = Image.new("RGB", size, BG)
    resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
    copy = image.convert("RGB")
    copy.thumbnail(size, resample)
    x = (size[0] - copy.width) // 2
    y = (size[1] - copy.height) // 2
    fitted.paste(copy, (x, y))
    return fitted
