"""Export a static Cloudflare Pages site from the local database. Read-only.

Site chrome lives in site/index.html plus cache-busted briefing-*.css/js.
This exporter writes JSON and copies daily files; it does not overwrite the reader UX.
"""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config.logging import STAGE_REPORT, get_logger, log_stage
from app.config.settings import PROJECT_ROOT
from app.dashboard_data import dashboard_stats, filter_options, list_reports, search_items
from app.site_rss import write_public_feeds
from app.utils.dates import today_ist

logger = get_logger(__name__)

SITE_DIR = PROJECT_ROOT / "site"
ARCHIVE_START = date(2026, 8, 17)

_LEGACY_NAMES = {
    "markdown": "report.md",
    "html": "report.html",
    "pdf": "report.pdf",
    "infographic": "report-infographic.png",
    "video": "report-briefing.gif",
    "mp4": "report-briefing.mp4",
}

_EXEC_ITEM = re.compile(r"^\d+\.\s+\*\*(.+?)\*\*\s+[—–-]\s+(.*)$")
_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_SOURCE_INLINE = re.compile(
    r"Source:\s+\[(.+?)\]\((.+?)\)(?:\s*[·•—–-]\s*(\d{4}-\d{2}-\d{2}))?"
)


@dataclass
class SiteExportSummary:
    site_dir: str = ""
    items: int = 0
    reports: int = 0
    files_copied: int = 0
    dates: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        lines = [
            f"Cloudflare site: {self.site_dir}",
            f"Items exported: {self.items}",
            f"Reports exported: {self.reports}",
            f"Files copied: {self.files_copied}",
        ]
        if self.errors:
            lines.append("Errors:")
            lines.extend(f"  - {error}" for error in self.errors)
        return "\n".join(lines)


def export_public_site(session: Session, site_dir: Path | None = None) -> SiteExportSummary:
    """Write dashboard + history JSON and copy every stored report into site/files/."""
    root = Path(site_dir) if site_dir is not None else SITE_DIR
    summary = SiteExportSummary(site_dir=str(root))
    data_dir = root / "data"
    files_dir = root / "files"
    data_dir.mkdir(parents=True, exist_ok=True)
    files_dir.mkdir(parents=True, exist_ok=True)

    try:
        by_date = {
            key: value
            for key, value in _load_archive(data_dir).items()
            if _is_archive_date(key)
        }
        copied = 0
        for report in list_reports(session):
            date_key = str(report.get("report_date") or "")
            if not _is_archive_date(date_key):
                continue
            public, n = _public_report(report, files_dir)
            previous = by_date.get(date_key) or {}
            if not public.get("files") and previous.get("files"):
                public["files"] = previous["files"]
            if not public.get("preview") and previous.get("preview"):
                public["preview"] = previous["preview"]
            if not public.get("briefing") and previous.get("briefing"):
                public["briefing"] = previous["briefing"]
            _remove_legacy_duplicates(files_dir / date_key, date_key)
            zip_url = _write_day_zip(files_dir / date_key, date_key)
            if zip_url:
                files = dict(public.get("files") or {})
                files["zip"] = zip_url
                public["files"] = files
            by_date[date_key] = public
            copied += n

        for folder in files_dir.iterdir():
            if not folder.is_dir() or not _is_archive_date(folder.name):
                continue
            _remove_legacy_duplicates(folder, folder.name)
            disk_files = _files_from_site_folder(folder)
            zip_url = _write_day_zip(folder, folder.name)
            if zip_url:
                disk_files["zip"] = zip_url
            if not disk_files:
                continue
            existing = by_date.get(folder.name)
            if existing is None:
                existing = {
                    "id": None,
                    "report_date": folder.name,
                    "title": "AI Daily Intelligence",
                    "stats": {},
                    "preview": "",
                    "files": disk_files,
                }
                by_date[folder.name] = existing
            else:
                merged = dict(existing.get("files") or {})
                merged.update({key: value for key, value in disk_files.items() if value})
                existing["files"] = merged
            _hydrate_briefing(existing, folder)

        public_reports = sorted(
            by_date.values(),
            key=lambda row: str(row.get("report_date") or ""),
            reverse=True,
        )
        for row in public_reports:
            date_key = str(row.get("report_date") or "")
            if not date_key:
                continue
            folder = files_dir / date_key
            _hydrate_briefing(row, folder)
            if _ensure_day_pdf(folder, date_key, row):
                copied += 1
            if _ensure_day_video(
                folder,
                date_key,
                row,
                generate=_should_generate_video(date_key, public_reports, folder),
            ):
                copied += 1
            zip_url = _write_day_zip(folder, date_key)
            if zip_url:
                files = dict(row.get("files") or {})
                files["zip"] = zip_url
                row["files"] = files
        generated_at = datetime.now(timezone.utc)
        payload = {
            "generated_at": generated_at.isoformat(),
            "today": _today_iso(),
            "stats": dashboard_stats(session),
            "options": filter_options(session),
            "items": search_items(session, limit=80),
            "archive_start": ARCHIVE_START.isoformat(),
            "reports": public_reports,
        }
        history = {
            "generated_at": generated_at.isoformat(),
            "today": payload["today"],
            "archive_start": ARCHIVE_START.isoformat(),
            "count": len(public_reports),
            "dates": [row.get("report_date") for row in public_reports],
            "reports": public_reports,
        }
        (data_dir / "dashboard.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "history.json").write_text(
            json.dumps(history, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        write_public_feeds(root, public_reports, generated_at=generated_at)
        summary.items = len(payload["items"])
        summary.reports = len(public_reports)
        summary.files_copied = copied
        summary.dates = [str(row.get("report_date") or "") for row in public_reports]
        log_stage(
            logger,
            STAGE_REPORT,
            "cloudflare site items=%s reports=%s files=%s",
            summary.items,
            summary.reports,
            copied,
        )
    except Exception as exc:  # noqa: BLE001
        summary.errors.append(str(exc))
        log_stage(logger, STAGE_REPORT, "site export failed error=%s", exc, level=40)
    return summary


def parse_briefing(markdown: str) -> dict[str, Any]:
    """Turn daily-report markdown into sections the archive reader can render."""
    text = (markdown or "").replace("\r\n", "\n")
    if not text.strip():
        return {}
    lines = text.split("\n")
    title = "AI Daily Intelligence"
    report_date = ""
    stats_line = ""
    executive: list[dict[str, str]] = []
    sections: list[dict[str, Any]] = []
    watch: list[str] = []
    sources: list[dict[str, str]] = []
    heading = ""
    current_section: dict[str, Any] | None = None
    current_item: dict[str, str] | None = None

    def flush_item() -> None:
        nonlocal current_item
        if current_item is not None and current_section is not None:
            current_section.setdefault("items", []).append(current_item)
        current_item = None

    def flush_section() -> None:
        nonlocal current_section
        flush_item()
        if current_section is not None:
            sections.append(current_section)
        current_section = None

    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped.startswith("# ") and not heading and not executive:
            title = stripped[2:].strip() or title
            index += 1
            continue
        if stripped.startswith("**Date:**"):
            report_date = stripped.replace("**Date:**", "").strip()
            index += 1
            continue
        if stripped.startswith("*") and stripped.endswith("*") and "consider" in stripped.lower():
            stats_line = stripped.strip("*").strip()
            index += 1
            continue
        if stripped.startswith("## "):
            flush_section()
            heading = stripped[3:].strip()
            if heading == "Executive Summary":
                index += 1
                while index < len(lines) and not lines[index].startswith("## "):
                    row = lines[index].strip()
                    match = _EXEC_ITEM.match(row)
                    if match:
                        why = match.group(2).strip()
                        item = {
                            "title": match.group(1).strip(),
                            "summary": why,
                            "why_it_matters": why,
                            "source_name": "",
                            "source_url": "",
                            "published_at": "",
                        }
                        index += 1
                        if index < len(lines):
                            source_match = _SOURCE_INLINE.search(lines[index].strip())
                            if source_match:
                                item["source_name"] = source_match.group(1).strip()
                                item["source_url"] = source_match.group(2).strip()
                                item["published_at"] = (source_match.group(3) or "").strip()
                                index += 1
                        executive.append(item)
                        continue
                    index += 1
                continue
            if heading == "What to Watch":
                index += 1
                while index < len(lines) and not lines[index].startswith("## "):
                    row = lines[index].strip()
                    if row.startswith("- "):
                        watch.append(row[2:].strip())
                    index += 1
                continue
            if heading == "Sources":
                index += 1
                while index < len(lines) and not lines[index].startswith("## "):
                    row = lines[index].strip()
                    link = _MD_LINK.search(row)
                    if row.startswith("- ") and link:
                        sources.append({"name": link.group(1).strip(), "url": link.group(2).strip()})
                    index += 1
                continue
            current_section = {"heading": heading, "items": []}
            index += 1
            continue
        if stripped.startswith("### ") and current_section is not None:
            flush_item()
            current_item = {
                "title": stripped[4:].strip(),
                "body": "",
                "problem": "",
                "key_contribution": "",
                "why_it_matters": "",
                "source_name": "",
                "source_url": "",
                "published_at": "",
            }
            index += 1
            continue
        if current_item is not None:
            if stripped.startswith("**Problem:**"):
                current_item["problem"] = stripped.replace("**Problem:**", "").strip()
            elif stripped.startswith("**Key contribution:**"):
                current_item["key_contribution"] = stripped.replace("**Key contribution:**", "").strip()
            elif stripped.startswith("**Why it matters:**"):
                current_item["why_it_matters"] = stripped.replace("**Why it matters:**", "").strip()
            elif stripped.startswith("**Source:**"):
                link = _MD_LINK.search(stripped)
                if link:
                    current_item["source_name"] = link.group(1).strip()
                    current_item["source_url"] = link.group(2).strip()
                if "—" in stripped:
                    current_item["published_at"] = stripped.split("—", 1)[-1].strip()
            elif stripped.startswith("**Supporting sources:**"):
                current_item["supporting"] = stripped.replace("**Supporting sources:**", "").strip()
            elif stripped.startswith("*Validation notes:*"):
                current_item["notes"] = stripped.replace("*Validation notes:*", "").strip()
            elif stripped and not stripped.startswith("No items"):
                current_item["body"] = (
                    f"{current_item['body']} {stripped}".strip() if current_item["body"] else stripped
                )
            index += 1
            continue
        index += 1
    flush_section()
    return {
        "title": title,
        "date": report_date,
        "stats_line": stats_line,
        "lede": _lede_from_executive(executive),
        "executive": executive,
        "sections": sections,
        "watch": watch,
        "sources": sources,
    }


def _lede_from_executive(executive: list[dict[str, str]]) -> str:
    """One-line masthead dek: what moved today, not a pipeline status line."""
    titles: list[str] = []
    selected: list[str] = []
    for item in executive:
        raw = str(item.get("title") or "").strip()
        if not raw or _is_near_duplicate_title(raw, selected):
            continue
        selected.append(raw)
        titles.append(_clip_lede_title(raw))
        if len(titles) == 3:
            break
    if not titles:
        return "The day’s ranked AI stories, in one sitting."
    if len(titles) == 1:
        return titles[0]
    if len(titles) == 2:
        return f"{titles[0]}, and {titles[1]}"
    return f"{titles[0]}; {titles[1]}; and {titles[2]}"


_GENERIC_TITLE_WORDS = {
    "openai",
    "google",
    "microsoft",
    "amazon",
    "meta",
    "anthropic",
    "nvidia",
    "intel",
    "apple",
    "deepmind",
}


def _is_near_duplicate_title(title: str, existing: list[str]) -> bool:
    words = _significant_words(title)
    for other in existing:
        shared = [word for word in _significant_words(other) if word in words]
        distinctive = [word for word in shared if word not in _GENERIC_TITLE_WORDS]
        if any(len(word) >= 8 for word in distinctive) or len(distinctive) >= 2:
            return True
    return False


def _significant_words(title: str) -> list[str]:
    folded = "".join(
        ch.lower() if ch.isalnum() else " "
        for ch in unicodedata.normalize("NFD", title)
        if unicodedata.category(ch) != "Mn"
    )
    return [word for word in folded.split() if len(word) > 4]


def _clip_lede_title(title: str, limit: int = 58) -> str:
    text = " ".join(title.split())
    if len(text) <= limit:
        return text.rstrip(",:;.—-")
    cut = text[:limit].rsplit(" ", 1)[0]
    stop = {"and", "or", "the", "a", "an", "of", "for", "to", "in", "with", "as"}
    parts = cut.split()
    while parts and parts[-1].lower().strip(",:;.—-") in stop:
        parts.pop()
    return " ".join(parts).rstrip(",:;.—-") or text[:limit]


def _today_iso() -> str:
    return today_ist().isoformat()


def _preview_text(markdown: str, limit: int = 4000) -> str:
    text = markdown or ""
    if len(text) > limit:
        return text[:limit].rstrip() + "\n\n…"
    return text


def _read_site_markdown(folder: Path, date_key: str | None = None) -> str:
    if not folder.is_dir():
        return ""
    key = date_key or folder.name
    names = [_public_filenames(key)["markdown"], _LEGACY_NAMES["markdown"]]
    for name in names:
        path = folder / name
        if not path.is_file():
            continue
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""
    return ""


def _hydrate_briefing(row: dict[str, Any], folder: Path) -> None:
    """Fill structured briefing from the day's markdown so the site can render it."""
    existing = row.get("briefing") if isinstance(row.get("briefing"), dict) else {}
    markdown = _read_site_markdown(folder, str(row.get("report_date") or folder.name))
    if not markdown.strip():
        preview = str(row.get("preview") or "")
        if preview and not preview.rstrip().endswith("…"):
            markdown = preview
    if not markdown.strip():
        if existing:
            row["briefing"] = existing
        return
    parsed = parse_briefing(markdown)
    if parsed.get("executive") or parsed.get("sections") or parsed.get("watch"):
        row["briefing"] = parsed
    elif existing:
        row["briefing"] = existing
    if not row.get("preview"):
        row["preview"] = _preview_text(markdown)
    if parsed.get("title") and row.get("title") in {None, "", "AI Daily Intelligence"}:
        row["title"] = parsed["title"]


def _ensure_day_pdf(folder: Path, date_key: str, row: dict[str, Any]) -> bool:
    """Copy or generate the day's PDF so the public download is never a dead link."""
    filename = _public_filenames(date_key)["pdf"]
    target = folder / filename
    files = dict(row.get("files") or {})
    if target.is_file() and target.stat().st_size > 0:
        files["pdf"] = f"files/{date_key}/{filename}"
        row["files"] = files
        return False
    folder.mkdir(parents=True, exist_ok=True)
    source = PROJECT_ROOT / "data" / "reports" / filename
    created = False
    if source.is_file() and source.stat().st_size > 0:
        shutil.copy2(source, target)
        created = True
    else:
        briefing = row.get("briefing") if isinstance(row.get("briefing"), dict) else {}
        if not (briefing.get("executive") or briefing.get("sections")):
            markdown = _read_site_markdown(folder, date_key)
            if markdown.strip():
                briefing = parse_briefing(markdown)
        if not (briefing.get("executive") or briefing.get("sections") or briefing.get("watch")):
            return False
        try:
            from app.report.pdf import write_pdf

            write_pdf(_document_from_briefing(date_key, briefing, row.get("stats") or {}), target)
            created = target.is_file() and target.stat().st_size > 0
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not write PDF for %s: %s", date_key, exc)
            return False
    if not created:
        return False
    files["pdf"] = f"files/{date_key}/{filename}"
    row["files"] = files
    return True


def _should_generate_video(
    date_key: str,
    public_reports: list[dict[str, Any]],
    folder: Path | None = None,
) -> bool:
    """Encode MP4 for today, the latest edition, and archive days that still lack video."""
    today = _today_iso()
    latest = str((public_reports[0] or {}).get("report_date") or "") if public_reports else ""
    if date_key in {today, latest}:
        return True
    if folder is None:
        return False
    mp4 = folder / _public_filenames(date_key)["mp4"]
    return not (mp4.is_file() and mp4.stat().st_size > 32)


def _ensure_day_video(folder: Path, date_key: str, row: dict[str, Any], *, generate: bool) -> bool:
    """Copy or encode the day's MP4. Missing ffmpeg leaves the GIF; never fails export."""
    names = _public_filenames(date_key)
    mp4_name = names["mp4"]
    gif_name = names["video"]
    folder.mkdir(parents=True, exist_ok=True)
    files = dict(row.get("files") or {})
    mp4_target = folder / mp4_name
    gif_target = folder / gif_name
    created = False

    if gif_target.is_file() and gif_target.stat().st_size > 0:
        files["video"] = f"files/{date_key}/{gif_name}"

    if mp4_target.is_file() and mp4_target.stat().st_size > 32:
        files["mp4"] = f"files/{date_key}/{mp4_name}"
        row["files"] = files
        return False

    source = PROJECT_ROOT / "data" / "reports" / mp4_name
    if source.is_file() and source.stat().st_size > 32:
        shutil.copy2(source, mp4_target)
        files["mp4"] = f"files/{date_key}/{mp4_name}"
        row["files"] = files
        return True

    if not generate:
        row["files"] = files
        return False

    briefing = row.get("briefing") if isinstance(row.get("briefing"), dict) else {}
    if not (briefing.get("executive") or briefing.get("sections")):
        markdown = _read_site_markdown(folder, date_key)
        if markdown.strip():
            briefing = parse_briefing(markdown)
    if not (briefing.get("executive") or briefing.get("sections") or briefing.get("watch")):
        row["files"] = files
        return False

    try:
        from PIL import Image

        from app.media.video import build_slides, encode_mp4

        document = _document_from_briefing(date_key, briefing, row.get("stats") or {})
        infographic = None
        info_path = folder / names["infographic"]
        if info_path.is_file():
            infographic = Image.open(info_path)
        slides = build_slides(document, infographic_image=infographic)
        encoded = encode_mp4(slides, mp4_target, allow_download=True)
        if infographic is not None:
            infographic.close()
        if encoded is not None and encoded.is_file() and encoded.stat().st_size > 32:
            files["mp4"] = f"files/{date_key}/{mp4_name}"
            created = True
        if not gif_target.is_file():
            from app.media.builder import write_media_pack

            bundle = write_media_pack(document, out_dir=folder, stem=f"ai-daily-intelligence-{date_key}")
            if bundle.video_path and Path(bundle.video_path).is_file():
                files["video"] = f"files/{date_key}/{gif_name}"
                created = True
            if bundle.mp4_path and Path(bundle.mp4_path).is_file() and "mp4" not in files:
                files["mp4"] = f"files/{date_key}/{mp4_name}"
                created = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not write video for %s: %s", date_key, exc)
        row["files"] = files
        return False
    row["files"] = files
    return created


def _document_from_briefing(date_key: str, briefing: dict[str, Any], stats: dict[str, Any]):
    from app.report.models import DailyReportDocument, ReportItem

    def to_item(raw: dict[str, Any], index: int) -> ReportItem:
        return ReportItem(
            article_id=index,
            title=str(raw.get("title") or "Untitled"),
            summary=str(raw.get("summary") or raw.get("body") or ""),
            why_it_matters=str(raw.get("why_it_matters") or ""),
            problem=str(raw.get("problem") or ""),
            key_contribution=str(raw.get("key_contribution") or ""),
            source_name=str(raw.get("source_name") or "Source"),
            source_url=str(raw.get("source_url") or ""),
            published_at=raw.get("published_at") or None,
        )

    executive = [to_item(item, index) for index, item in enumerate(briefing.get("executive") or [])]
    developments: list[ReportItem] = []
    research: list[ReportItem] = []
    industry: list[ReportItem] = []
    for section in briefing.get("sections") or []:
        heading = str(section.get("heading") or "").lower()
        items = [to_item(item, index) for index, item in enumerate(section.get("items") or [])]
        if "research" in heading:
            research.extend(items)
        elif "industry" in heading or "product" in heading:
            industry.extend(items)
        else:
            developments.extend(items)
    sources: list[tuple[str, str]] = []
    for src in briefing.get("sources") or []:
        if isinstance(src, dict):
            sources.append((str(src.get("name") or ""), str(src.get("url") or "")))
    return DailyReportDocument(
        title=str(briefing.get("title") or "AI Daily Intelligence"),
        report_date=date.fromisoformat(date_key),
        executive=executive,
        developments=developments,
        research=research,
        industry=industry,
        watch=[str(item) for item in (briefing.get("watch") or [])],
        sources=sources,
        stats={
            "candidates": stats.get("candidates") or 0,
            "selected": stats.get("selected") or len(executive),
            "flagged": stats.get("flagged") or 0,
        },
    )


def _is_archive_date(date_key: str) -> bool:
    try:
        return date.fromisoformat(date_key) >= ARCHIVE_START
    except ValueError:
        return False


def _load_archive(data_dir: Path) -> dict[str, dict[str, Any]]:
    """Keep previously exported reports so a new day does not wipe the archive."""
    by_date: dict[str, dict[str, Any]] = {}
    for name in ("history.json", "dashboard.json"):
        path = data_dir / name
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for row in payload.get("reports") or []:
            date_key = str(row.get("report_date") or "")
            if date_key and date_key not in by_date:
                by_date[date_key] = row
    return by_date


def _public_filenames(date_key: str) -> dict[str, str]:
    prefix = f"ai-daily-intelligence-{date_key}"
    return {
        "markdown": f"{prefix}.md",
        "html": f"{prefix}.html",
        "pdf": f"{prefix}.pdf",
        "infographic": f"{prefix}-infographic.png",
        "video": f"{prefix}-briefing.gif",
        "mp4": f"{prefix}-briefing.mp4",
    }


def _public_report(report: dict[str, Any], files_dir: Path) -> tuple[dict[str, Any], int]:
    date_key = str(report.get("report_date") or "report")
    dest = files_dir / date_key
    dest.mkdir(parents=True, exist_ok=True)
    files = report.get("files") or {}
    stats = report.get("stats") or {}
    public_files: dict[str, Any] = {}
    copied = 0

    for label, filename in _public_filenames(date_key).items():
        source = files.get(label) or stats.get(f"{label}_path")
        copied_path = _copy_named(source, dest, filename)
        if copied_path:
            public_files[label] = copied_path
            copied += 1

    card_urls = []
    for index, source in enumerate(files.get("cards") or stats.get("card_paths") or [], start=1):
        copied_path = _copy_named(source, dest, f"ai-daily-intelligence-{date_key}-card-{index:02d}.png")
        if copied_path:
            card_urls.append(copied_path)
            copied += 1
    if card_urls:
        public_files["cards"] = card_urls

    if not public_files:
        public_files = _files_from_site_folder(dest)
    else:
        extras = _files_from_site_folder(dest)
        for key, value in extras.items():
            if key == "cards":
                public_files.setdefault("cards", value)
            else:
                public_files.setdefault(key, value)

    markdown = str(report.get("markdown_content") or "")
    if not markdown.strip():
        markdown = _read_site_markdown(dest, date_key)
    preview = _preview_text(markdown)
    briefing = parse_briefing(markdown) if markdown.strip() else {}

    return (
        {
            "id": report.get("id"),
            "report_date": report.get("report_date"),
            "title": report.get("title"),
            "stats": {
                "candidates": stats.get("candidates"),
                "selected": stats.get("selected"),
                "flagged": stats.get("flagged"),
            },
            "preview": preview,
            "briefing": briefing,
            "files": public_files,
        },
        copied,
    )


def _files_from_site_folder(dest: Path) -> dict[str, Any]:
    if not dest.is_dir():
        return {}
    public: dict[str, Any] = {}
    date_key = dest.name
    for label, filename in _public_filenames(date_key).items():
        candidates = [filename]
        if label in _LEGACY_NAMES:
            candidates.append(_LEGACY_NAMES[label])
        for candidate in candidates:
            if (dest / candidate).is_file():
                public[label] = f"files/{date_key}/{candidate}"
                break
    cards = sorted(
        path.name
        for path in dest.glob("*.png")
        if path.name.startswith(f"ai-daily-intelligence-{date_key}-card-") or path.name.startswith("card-")
    )
    if cards:
        public["cards"] = [f"files/{date_key}/{name}" for name in cards]
    zip_name = f"ai-daily-intelligence-{date_key}.zip"
    if (dest / zip_name).is_file():
        public["zip"] = f"files/{date_key}/{zip_name}"
    return public


def _remove_legacy_duplicates(dest: Path, date_key: str) -> None:
    if not dest.is_dir():
        return
    dated = _public_filenames(date_key)
    for label, legacy_name in _LEGACY_NAMES.items():
        legacy = dest / legacy_name
        current = dest / dated[label]
        if legacy.is_file() and current.is_file() and legacy.resolve() != current.resolve():
            legacy.unlink()
    for path in dest.glob("card-*.png"):
        dated_card = dest / f"ai-daily-intelligence-{date_key}-{path.name}"
        if dated_card.is_file():
            path.unlink()


def _write_day_zip(dest: Path, date_key: str) -> str | None:
    if not dest.is_dir():
        return None
    members = [
        path
        for path in sorted(dest.iterdir())
        if path.is_file() and path.suffix.lower() != ".zip"
    ]
    if not members:
        return None
    zip_name = f"ai-daily-intelligence-{date_key}.zip"
    zip_path = dest / zip_name
    folder = f"ai-daily-intelligence-{date_key}"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in members:
            archive.write(path, arcname=f"{folder}/{path.name}")
    return f"files/{date_key}/{zip_name}"


def _copy_named(source: Any, dest: Path, filename: str) -> str | None:
    if not source or not isinstance(source, str):
        return None
    path = Path(source)
    if not path.is_file():
        return None
    target = dest / filename
    shutil.copy2(path, target)
    return f"files/{dest.name}/{filename}"
