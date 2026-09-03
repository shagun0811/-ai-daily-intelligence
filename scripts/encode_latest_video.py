"""Encode briefing MP4s and free neural audio for today / missing archive days."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image

from app.media.audio import write_briefing_audio
from app.media.video import build_slides, encode_mp4, find_ffmpeg, mp4_has_audio, mux_narration
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
        audio_dest = folder / names["audio"]
        force = date_key == today or folder == days[0]
        md = folder / names["markdown"]
        if not md.is_file():
            print(f"skip {date_key}: no markdown")
            continue
        briefing = parse_briefing(md.read_text(encoding="utf-8"))
        document = _document_from_briefing(date_key, briefing, {})
        if dest.is_file() and dest.stat().st_size > 32:
            skipped += 1
        else:
            info_path = folder / names["infographic"]
            infographic = Image.open(info_path) if info_path.is_file() else None
            slides = build_slides(document, infographic_image=infographic)
            print(f"day={date_key} stories={len(briefing.get('executive') or [])} slides={len(slides)}")
            path = encode_mp4(slides, dest, allow_download=True)
            if infographic is not None:
                infographic.close()
            if path is None:
                print(f"mp4 not written for {date_key} (ffmpeg missing); GIF fallback stays")
            else:
                print(f"wrote {path} bytes={path.stat().st_size}")
                wrote += 1
        if not force:
            continue
        if force:
            audio = write_briefing_audio(document, audio_dest, enabled=True)
            if audio is None:
                print(f"audio not written for {date_key} (edge-tts missing or failed)")
            else:
                print(f"wrote {audio} bytes={audio.stat().st_size}")
                wrote += 1
            reports = ROOT / "data" / "reports"
            if audio is not None:
                reports.mkdir(parents=True, exist_ok=True)
                copied = reports / audio.name
                if copied.resolve() != audio.resolve():
                    copied.write_bytes(audio.read_bytes())
        if (
            force
            and audio_dest.is_file()
            and audio_dest.stat().st_size > 32
            and dest.is_file()
            and dest.stat().st_size > 32
            and not mp4_has_audio(dest)
        ):
            muxed = mux_narration(dest, audio_dest, dest)
            print(f"mux={'ok' if muxed else 'skipped'} {date_key}")
            if muxed:
                wrote += 1
                reports = ROOT / "data" / "reports"
                reports.mkdir(parents=True, exist_ok=True)
                (reports / dest.name).write_bytes(dest.read_bytes())
    print(f"encoded={wrote} already_present={skipped}")
    return 0 if wrote or skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
