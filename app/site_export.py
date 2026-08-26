"""Export a static Cloudflare Pages site from the local database. Read-only."""

from __future__ import annotations

import json
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.config.logging import STAGE_REPORT, get_logger, log_stage
from app.config.settings import PROJECT_ROOT
from app.dashboard_data import dashboard_stats, filter_options, list_reports, search_items

logger = get_logger(__name__)

SITE_DIR = PROJECT_ROOT / "site"
ARCHIVE_START = date(2026, 8, 17)

_LEGACY_NAMES = {
    "markdown": "report.md",
    "html": "report.html",
    "pdf": "report.pdf",
    "infographic": "report-infographic.png",
    "video": "report-briefing.gif",
}

_EXEC_ITEM = re.compile(r"^\d+\.\s+\*\*(.+?)\*\*\s+[—–-]\s+(.*)$")
_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_SOURCE_INLINE = re.compile(r"Source:\s+\[(.+?)\]\((.+?)\)")


@dataclass
class SiteExportSummary:
    site_dir: str = ""
    items: int = 0
    reports: int = 0
    files_copied: int = 0
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
            if date_key:
                _hydrate_briefing(row, files_dir / date_key)
        generated_at = datetime.now(timezone.utc).isoformat()
        payload = {
            "generated_at": generated_at,
            "today": _today_iso(),
            "stats": dashboard_stats(session),
            "options": filter_options(session),
            "items": search_items(session, limit=80),
            "archive_start": ARCHIVE_START.isoformat(),
            "reports": public_reports,
        }
        history = {
            "generated_at": generated_at,
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
        summary.items = len(payload["items"])
        summary.reports = len(public_reports)
        summary.files_copied = copied
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
                        item = {
                            "title": match.group(1).strip(),
                            "summary": match.group(2).strip(),
                            "source_name": "",
                            "source_url": "",
                        }
                        index += 1
                        if index < len(lines):
                            source_match = _SOURCE_INLINE.search(lines[index].strip())
                            if source_match:
                                item["source_name"] = source_match.group(1).strip()
                                item["source_url"] = source_match.group(2).strip()
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
        "executive": executive,
        "sections": sections,
        "watch": watch,
        "sources": sources,
    }


def _today_iso() -> str:
    try:
        zone = ZoneInfo("Asia/Kolkata")
    except ZoneInfoNotFoundError:
        zone = timezone.utc
    return datetime.now(zone).date().isoformat()


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
        for candidate in (filename, _LEGACY_NAMES[label]):
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
