"""One-off: encode the newest archive day's MP4 using local ffmpeg."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image

from app.media.video import build_slides, encode_mp4, find_ffmpeg
from app.site_export import parse_briefing, _document_from_briefing


def main() -> int:
    files = ROOT / "site" / "files"
    days = sorted((path for path in files.iterdir() if path.is_dir()), reverse=True)
    if not days:
        print("no archive days")
        return 1
    folder = days[0]
    date_key = folder.name
    md = folder / f"ai-daily-intelligence-{date_key}.md"
    if not md.is_file():
        print(f"missing {md}")
        return 1
    briefing = parse_briefing(md.read_text(encoding="utf-8"))
    document = _document_from_briefing(date_key, briefing, {})
    info_path = folder / f"ai-daily-intelligence-{date_key}-infographic.png"
    infographic = Image.open(info_path) if info_path.is_file() else None
    slides = build_slides(document, infographic_image=infographic)
    dest = folder / f"ai-daily-intelligence-{date_key}-briefing.mp4"
    print(f"day={date_key} stories={len(briefing.get('executive') or [])} slides={len(slides)}")
    print(f"ffmpeg={find_ffmpeg(allow_download=True)}")
    path = encode_mp4(slides, dest, allow_download=True)
    if infographic is not None:
        infographic.close()
    if path is None:
        print("mp4 not written (ffmpeg missing); GIF fallback stays")
        return 1
    print(f"wrote {path} bytes={path.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
