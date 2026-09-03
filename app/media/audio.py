"""Free neural briefing audio via Microsoft Edge TTS (edge-tts). No API key.

Windows and GitHub Ubuntu both work. If TTS is missing or fails, callers keep
the silent video and hide Listen — this module never raises for that.
"""

from __future__ import annotations

import asyncio
import os
import re
from datetime import date
from pathlib import Path

from app.config.logging import STAGE_REPORT, get_logger, log_stage
from app.report.models import DailyReportDocument, ReportItem

logger = get_logger(__name__)

DEFAULT_VOICE = "en-US-JennyNeural"
FALLBACK_VOICES = ("en-IN-NeerjaNeural", "en-US-AriaNeural")
MAX_STORIES = 5
MAX_WHY = 220
TTS_TIMEOUT_SECONDS = 90

_ORDINALS = (
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
)
_TITLE_SUFFIX = re.compile(
    r"\s+[-–—|]\s+(?:theguardian\.com|kron4|techcrunch|the verge|reuters|bloomberg|wired)\s*$",
    re.I,
)
_BARE_WHY = re.compile(r"^(not stated in the source\.?|n/?a|none)\s*$", re.I)


def build_briefing_script(document: DailyReportDocument) -> str:
    """Short spoken script: date, top headlines, one-line why-it-matters each."""
    day = document.report_date
    spoken_date = _spoken_date(day)
    stories = list(document.executive[:MAX_STORIES])
    lines = [
        f"This is the AI Daily Intelligence briefing for {spoken_date}.",
        "Here is what moved in AI today.",
    ]
    if not stories:
        lines.append("No ranked stories made the pack. The full write-up is on the site.")
        return " ".join(lines)

    for index, item in enumerate(stories):
        rank = _ORDINALS[index] if index < len(_ORDINALS) else str(index + 1)
        title = _spoken_title(item)
        why = _spoken_why(item, title)
        lines.append(f"Story {rank}. {title}.")
        if why:
            lines.append(f"Why it matters: {why}")
    lines.append("That's the briefing. Full sources and the PDF are on the site.")
    return " ".join(part.strip() for part in lines if part.strip())


def synthesize_audio(
    script: str,
    dest: Path,
    *,
    voice: str | None = None,
    enabled: bool | None = None,
) -> Path | None:
    """Write dest as MP3. Returns the path, or None if TTS is unavailable."""
    text = " ".join((script or "").split()).strip()
    if not text:
        return None
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if enabled is None:
        enabled = _tts_enabled()
    if not enabled:
        log_stage(logger, STAGE_REPORT, "audio skipped: TTS disabled for this run")
        return None
    edge_tts = _load_edge_tts()
    if edge_tts is None:
        log_stage(logger, STAGE_REPORT, "audio skipped: edge-tts not installed")
        return None
    voices = [voice or DEFAULT_VOICE, *FALLBACK_VOICES]
    seen: set[str] = set()
    for name in voices:
        if not name or name in seen:
            continue
        seen.add(name)
        if _speak_to(edge_tts, text, dest, name):
            log_stage(logger, STAGE_REPORT, "audio wrote %s voice=%s", dest.name, name)
            return dest
    dest.unlink(missing_ok=True)
    return None


def write_briefing_audio(
    document: DailyReportDocument,
    dest: Path,
    *,
    voice: str | None = None,
    enabled: bool | None = None,
) -> Path | None:
    """Build the day's script and synthesize it. Never raises."""
    try:
        script = build_briefing_script(document)
        return synthesize_audio(script, dest, voice=voice, enabled=enabled)
    except Exception as exc:  # noqa: BLE001
        log_stage(logger, STAGE_REPORT, "audio write failed error=%s", exc, level=30)
        return None


def _tts_enabled() -> bool:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    flag = (os.environ.get("ADI_SKIP_TTS") or "").strip().lower()
    return flag not in {"1", "true", "yes", "on"}


def _load_edge_tts():
    try:
        import edge_tts
    except ImportError:
        return None
    return edge_tts


def _speak_to(edge_tts, text: str, dest: Path, voice: str) -> bool:
    def factory():
        async def _save() -> None:
            communicate = edge_tts.Communicate(text, voice, rate="-8%")
            await communicate.save(str(dest))

        return _save()

    try:
        _run_async(factory)
    except Exception as exc:  # noqa: BLE001
        log_stage(logger, STAGE_REPORT, "audio voice=%s failed error=%s", voice, exc, level=30)
        dest.unlink(missing_ok=True)
        return False
    return dest.is_file() and dest.stat().st_size > 32


def _run_async(factory) -> None:
    def go() -> None:
        asyncio.run(asyncio.wait_for(factory(), timeout=TTS_TIMEOUT_SECONDS))

    try:
        go()
        return
    except RuntimeError:
        pass

    error: list[BaseException] = []

    def worker() -> None:
        try:
            go()
        except BaseException as exc:  # noqa: BLE001
            error.append(exc)

    import threading

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout=TTS_TIMEOUT_SECONDS + 5)
    if error:
        raise error[0]
    if thread.is_alive():
        raise TimeoutError("edge-tts timed out")


def _spoken_date(day: date) -> str:
    weekday = day.strftime("%A")
    month = day.strftime("%B")
    return f"{weekday}, {month} {_ordinal(day.day)}, {day.year}"


def _ordinal(value: int) -> str:
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def _spoken_title(item: ReportItem) -> str:
    title = _TITLE_SUFFIX.sub("", (item.title or "").strip())
    title = re.sub(r"\s+", " ", title).strip(" -–—")
    return title or "Untitled story"


_DOMAINISH = re.compile(r"^(?:www\.)?[\w-]+(?:\.[\w-]+)+(?:[/?#].*)?$", re.I)


def _spoken_why(item: ReportItem, title: str) -> str:
    raw = (item.why_it_matters or item.summary or "").strip()
    if not raw or _BARE_WHY.match(raw):
        return ""
    text = re.sub(r"https?://\S+", "", raw)
    text = _TITLE_SUFFIX.sub("", text)
    text = re.sub(r"\s+", " ", text).strip(" -–—.")
    folded_title = re.sub(r"\W+", "", title).lower()
    folded_why = re.sub(r"\W+", "", text).lower()
    if folded_why and folded_title and folded_why.startswith(folded_title[:48]):
        rest = text[len(title) :].lstrip(" —–-.")
        text = rest or ""
    text = _TITLE_SUFFIX.sub("", text).strip(" -–—.")
    if not text or _BARE_WHY.match(text) or _DOMAINISH.match(text) or len(text) < 28:
        return ""
    if len(text) > MAX_WHY:
        cut = text[:MAX_WHY].rsplit(" ", 1)[0].rstrip(",;:.—-")
        text = f"{cut}." if cut else text[:MAX_WHY]
    if text and text[-1] not in ".!?":
        text += "."
    return text
