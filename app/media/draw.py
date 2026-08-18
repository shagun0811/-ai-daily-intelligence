"""Shared drawing helpers for briefing images. No LLM and no paid APIs."""

from __future__ import annotations

from pathlib import Path

from PIL import ImageFont

BG = (11, 16, 32)
PANEL = (21, 27, 46)
ACCENT = (62, 224, 197)
GOLD = (232, 196, 124)
TEXT = (232, 237, 247)
MUTED = (139, 151, 179)
TITLE = (244, 247, 255)
BAR_TRACK = (30, 38, 62)

_FONT_CANDIDATES = (
    Path(r"C:\Windows\Fonts\segoeui.ttf"),
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
)


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def wrap_text(draw, text: str, font, max_width: int, *, max_lines: int | None = None) -> list[str]:
    words = (text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
            continue
        lines.append(current)
        current = word
        if max_lines is not None and len(lines) >= max_lines:
            current = ""
            break
    if current and (max_lines is None or len(lines) < max_lines):
        lines.append(current)
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
    if max_lines is not None and lines:
        last = lines[-1]
        if draw.textlength(last, font=font) > max_width or len(words) > len(" ".join(lines).split()):
            lines[-1] = _ellipsis(draw, last, font, max_width)
    return lines


def _ellipsis(draw, text: str, font, max_width: int) -> str:
    suffix = "…"
    if draw.textlength(text + suffix, font=font) <= max_width:
        return text + suffix
    trimmed = text
    while trimmed and draw.textlength(trimmed + suffix, font=font) > max_width:
        trimmed = trimmed[:-1]
    return (trimmed or text[:1]) + suffix
