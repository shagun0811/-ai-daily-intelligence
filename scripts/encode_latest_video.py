"""Encode briefing MP4s for today and archive days that still lack video."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image

from app.media.video import build_slides, encode_mp4, find_ffmpeg
from app.site_export import _document_from_briefing, _public_filenames, parse_briefing
from app.utils.dates import today_ist


def main() -> int:
    files = ROOT / "site" / "files"
    if not files.is_dir():
        print("no archive days")
        return 1
    days = sorted((path for path in files.iterdir() if path.is_dir()), reverse=True)
    if not days:
        print("no archive days")
        return 1
    ffmpeg = find_ffmpeg(allow_download=True)
    print(f"ffmpeg={ffmpeg or 'missing'}")
    today = today_ist().isoformat()
    wrote = 0
    skipped = 0
    for folder in days:
        date_key = folder.name
        names = _public_filenames(date_key)
        dest = folder / names["mp4"]
        force = date_key == today or folder == days[0]
        if dest.is_file() and dest.stat().st_size > 32 and not force:
            skipped += 1
            continue
        md = folder / names["markdown"]
        if not md.is_file():
            print(f"skip {date_key}: no markdown")
            continue
        briefing = parse_briefing(md.read_text(encoding="utf-8"))
        document = _document_from_briefing(date_key, briefing, {})
        info_path = folder / names["infographic"]
        infographic = Image.open(info_path) if info_path.is_file() else None
        slides = build_slides(document, infographic_image=infographic)
        print(f"day={date_key} stories={len(briefing.get('executive') or [])} slides={len(slides)}")
        path = encode_mp4(slides, dest, allow_download=True)
        if infographic is not None:
            infographic.close()
        if path is None:
            print(f"mp4 not written for {date_key} (ffmpeg missing); GIF fallback stays")
            continue
        print(f"wrote {path} bytes={path.stat().st_size}")
        wrote += 1
    print(f"encoded={wrote} already_present={skipped}")
    return 0 if wrote or skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
