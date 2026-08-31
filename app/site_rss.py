"""Outbound RSS 2.0 / Atom feed of ranked daily briefing stories.

Generated during site export so the 1am and 5pm IST runs keep it fresh.
This is RSS *out* (subscribers), not inbound source collection.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, tzinfo, timezone
from email.utils import format_datetime
from hashlib import sha1
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PUBLIC_SITE_URL = "https://ai-daily-intelligence.pages.dev"
FEED_PATH = "/feed.xml"
RSS_ALIAS_PATH = "/rss.xml"
ATOM_PATH = "/atom.xml"
XSL_PATH = "/feed.xsl"
FEED_DAYS = 14
CHANNEL_TITLE = "AI Daily Intelligence"
CHANNEL_DESCRIPTION = (
    "Today’s ranked AI briefing: the stories that actually moved, and why they matter."
)
_PLACEHOLDER_WHY = re.compile(r"^not stated in the source\.?$", re.IGNORECASE)
_GOOGLE_NEWS_HOST = re.compile(r"(^|\.)news\.google\.", re.IGNORECASE)
_XSL_SOURCE = Path(__file__).with_name("feed.xsl")


def _ist() -> tzinfo:
    try:
        return ZoneInfo("Asia/Kolkata")
    except ZoneInfoNotFoundError:
        return timezone.utc


def write_public_feeds(
    site_dir: Any,
    reports: list[dict[str, Any]],
    *,
    generated_at: datetime | None = None,
) -> dict[str, int]:
    """Write feed.xml, rss.xml (duplicate), atom.xml, and feed.xsl into the site root."""
    root = Path(site_dir)
    root.mkdir(parents=True, exist_ok=True)
    built = generated_at or datetime.now(timezone.utc)
    rss = build_rss(reports, generated_at=built)
    atom = build_atom(reports, generated_at=built)
    xsl = _feed_xsl()
    (root / "feed.xml").write_text(rss, encoding="utf-8")
    (root / "rss.xml").write_text(rss, encoding="utf-8")
    (root / "atom.xml").write_text(atom, encoding="utf-8")
    (root / "feed.xsl").write_text(xsl, encoding="utf-8")
    return {
        "rss_bytes": len(rss.encode("utf-8")),
        "atom_bytes": len(atom.encode("utf-8")),
        "xsl_bytes": len(xsl.encode("utf-8")),
    }


def build_rss(
    reports: list[dict[str, Any]],
    *,
    generated_at: datetime | None = None,
) -> str:
    """Return a UTF-8 RSS 2.0 document for the newest FEED_DAYS editions."""
    built = _aware(generated_at or datetime.now(timezone.utc))
    items = _feed_items(reports)
    self_url = f"{PUBLIC_SITE_URL}{FEED_PATH}"
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<?xml-stylesheet type="text/xsl" href="{XSL_PATH}"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "<channel>",
        f"<title>{_xml(CHANNEL_TITLE)}</title>",
        f"<link>{_xml(PUBLIC_SITE_URL)}</link>",
        f"<description>{_xml(CHANNEL_DESCRIPTION)}</description>",
        "<language>en</language>",
        f"<lastBuildDate>{_rfc822(built)}</lastBuildDate>",
        f'<atom:link href="{_xml(self_url)}" rel="self" type="application/rss+xml"/>',
    ]
    for item in items:
        parts.extend(_rss_item(item))
    parts.extend(["</channel>", "</rss>", ""])
    return "\n".join(parts)


def build_atom(
    reports: list[dict[str, Any]],
    *,
    generated_at: datetime | None = None,
) -> str:
    """Return a UTF-8 Atom 1.0 document covering the same items as RSS."""
    built = _aware(generated_at or datetime.now(timezone.utc))
    items = _feed_items(reports)
    self_url = f"{PUBLIC_SITE_URL}{ATOM_PATH}"
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom">',
        f"<title>{_xml(CHANNEL_TITLE)}</title>",
        f'<link href="{_xml(PUBLIC_SITE_URL)}/" rel="alternate" type="text/html"/>',
        f'<link href="{_xml(self_url)}" rel="self" type="application/atom+xml"/>',
        f"<id>{_xml(PUBLIC_SITE_URL)}/</id>",
        f"<updated>{_iso8601(built)}</updated>",
        f"<subtitle>{_xml(CHANNEL_DESCRIPTION)}</subtitle>",
    ]
    for item in items:
        parts.extend(_atom_entry(item))
    parts.extend(["</feed>", ""])
    return "\n".join(parts)


def _feed_items(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Edition item plus ranked stories, newest day first, last FEED_DAYS editions."""
    rows = _recent_reports(reports)
    items: list[dict[str, Any]] = []
    for row in rows:
        date_key = str(row.get("report_date") or "").strip()
        if not date_key:
            continue
        edition_when = _edition_datetime(date_key)
        edition_url = f"{PUBLIC_SITE_URL}/#{date_key}"
        briefing = row.get("briefing") if isinstance(row.get("briefing"), dict) else {}
        stories = _ranked_stories(briefing)
        headlines = [story["title"] for story in stories[:8]]
        description = _edition_description(headlines)
        items.append(
            {
                "kind": "edition",
                "title": f"{CHANNEL_TITLE} — {date_key}",
                "link": edition_url,
                "guid": edition_url,
                "guid_permalink": True,
                "pub": edition_when,
                "description": description,
                "source_name": CHANNEL_TITLE,
                "source_url": edition_url,
            }
        )
        for index, story in enumerate(stories, start=1):
            source_url = story["source_url"] or edition_url
            why = story["why"] or story["title"]
            source_line = _source_line(story["source_name"], source_url)
            description = "\n\n".join(part for part in (why, source_line) if part)
            items.append(
                {
                    "kind": "story",
                    "title": story["title"],
                    "link": source_url,
                    "guid": _story_guid(date_key, index, story["title"], source_url),
                    "guid_permalink": False,
                    "pub": story["published_at"] or edition_when,
                    "description": description,
                    "source_name": story["source_name"] or CHANNEL_TITLE,
                    "source_url": source_url,
                }
            )
    return items


def _recent_reports(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dated: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for row in reports:
        date_key = str(row.get("report_date") or "").strip()
        if not date_key or date_key in seen:
            continue
        try:
            date.fromisoformat(date_key)
        except ValueError:
            continue
        seen.add(date_key)
        dated.append((date_key, row))
    dated.sort(key=lambda pair: pair[0], reverse=True)
    return [row for _, row in dated[:FEED_DAYS]]


def _ranked_stories(briefing: dict[str, Any]) -> list[dict[str, str | datetime | None]]:
    stories: list[dict[str, str | datetime | None]] = []
    seen: set[str] = set()

    def add(raw: dict[str, Any]) -> None:
        title = " ".join(str(raw.get("title") or "").split())
        if not title:
            return
        key = title.casefold()
        if key in seen:
            return
        seen.add(key)
        why = _story_why(raw, title)
        stories.append(
            {
                "title": title,
                "why": why,
                "source_name": str(raw.get("source_name") or "").strip(),
                "source_url": _prefer_article_url(
                    raw.get("canonical_url"),
                    raw.get("url"),
                    raw.get("article_url"),
                    raw.get("source_url"),
                ),
                "published_at": _parse_timestamp(raw.get("published_at")),
            }
        )

    for item in briefing.get("executive") or []:
        if isinstance(item, dict):
            add(item)
    if stories:
        return stories
    for section in briefing.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for item in section.get("items") or []:
            if isinstance(item, dict):
                add(item)
    return stories


def _story_guid(date_key: str, index: int, title: str, url: str) -> str:
    digest = sha1(f"{date_key}|{index}|{title}|{url}".encode("utf-8")).hexdigest()[:12]
    return f"tag:ai-daily-intelligence.pages.dev,{date_key}:story-{index}-{digest}"


def _edition_description(headlines: list[str]) -> str:
    """Full ranked headlines only — never a mid-word clipped lede."""
    complete = [title for title in headlines if title]
    if complete:
        return "Ranked stories: " + "; ".join(complete)
    return "The day’s ranked AI stories, in one sitting."


def _story_why(raw: dict[str, Any], title: str) -> str:
    """Prefer a real summary; never emit the unimplemented placeholder."""
    for key in ("why_it_matters", "summary", "body", "key_contribution", "problem"):
        text = _usable_prose(raw.get(key))
        if text:
            return text
    return title


def _usable_prose(value: Any) -> str:
    text = " ".join(str(value or "").split())
    if not text or _PLACEHOLDER_WHY.match(text):
        return ""
    return _end_on_complete_phrase(text)


def _end_on_complete_phrase(text: str) -> str:
    """If a summary was already clipped, stop on a full sentence or word — never mid-word."""
    stripped = text.strip()
    if stripped.endswith("..."):
        body = stripped[:-3].rstrip()
    elif stripped.endswith("…"):
        body = stripped[:-1].rstrip()
    else:
        return stripped
    for sep in (". ", "! ", "? "):
        idx = body.rfind(sep)
        if idx >= 24:
            return body[: idx + 1]
    parts = body.split()
    while parts and len(parts[-1].strip(".,;:—-")) <= 3:
        parts.pop()
    if not parts:
        return stripped
    return " ".join(parts).rstrip(".,;:—-") + "…"


def _prefer_article_url(*candidates: Any) -> str:
    """Publisher URL first; Google News wrapper only if that is all we have."""
    urls = [str(value or "").strip() for value in candidates if str(value or "").strip()]
    for url in urls:
        if not _is_google_news_url(url):
            return url
    return urls[0] if urls else ""


def _is_google_news_url(url: str) -> bool:
    host = urlsplit(url).netloc.lower()
    return bool(host and _GOOGLE_NEWS_HOST.search(host))


def _source_line(source_name: str, source_url: str) -> str:
    name = str(source_name or "").strip()
    if not name:
        return ""
    visible = _visible_source_url(source_url)
    if visible:
        return f"Source: {name} ({visible})"
    return f"Source: {name}"


def _visible_source_url(url: str) -> str:
    """Keep <link> as the real URL; do not dump Google News wrappers into body text."""
    text = str(url or "").strip()
    if not text or _is_google_news_url(text) or len(text) > 180:
        return ""
    return text


def _feed_xsl() -> str:
    if _XSL_SOURCE.is_file():
        return _XSL_SOURCE.read_text(encoding="utf-8")
    return _FALLBACK_XSL


def _rss_item(item: dict[str, Any]) -> list[str]:
    permalink = "true" if item.get("guid_permalink") else "false"
    lines = [
        "<item>",
        f"<title>{_xml(item['title'])}</title>",
        f"<link>{_xml(item['link'])}</link>",
        f'<guid isPermaLink="{permalink}">{_xml(item["guid"])}</guid>',
        f"<pubDate>{_rfc822(item['pub'])}</pubDate>",
        f"<description>{_xml(item['description'])}</description>",
    ]
    source_url = str(item.get("source_url") or "")
    source_name = str(item.get("source_name") or "")
    if source_url and source_name:
        lines.append(f'<source url="{_xml(source_url)}">{_xml(source_name)}</source>')
    lines.append("</item>")
    return lines


def _atom_entry(item: dict[str, Any]) -> list[str]:
    return [
        "<entry>",
        f"<title>{_xml(item['title'])}</title>",
        f'<link href="{_xml(item["link"])}" rel="alternate"/>',
        f"<id>{_xml(item['guid'])}</id>",
        f"<updated>{_iso8601(item['pub'])}</updated>",
        f"<published>{_iso8601(item['pub'])}</published>",
        f'<content type="text">{_xml(item["description"])}</content>',
        "</entry>",
    ]


def _edition_datetime(date_key: str) -> datetime:
    day = date.fromisoformat(date_key)
    return datetime.combine(day, time(17, 0), tzinfo=_ist())


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_ist())
        return parsed
    except ValueError:
        pass
    try:
        day = date.fromisoformat(text[:10])
        return datetime.combine(day, time(17, 0), tzinfo=_ist())
    except ValueError:
        return None


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _rfc822(value: datetime) -> str:
    return format_datetime(_aware(value))


def _iso8601(value: datetime) -> str:
    return _aware(value).isoformat()


def _xml(text: str) -> str:
    return escape(str(text or ""), {"\"": "&quot;", "'": "&apos;"})


_FALLBACK_XSL = """<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output method="html" encoding="UTF-8" indent="yes"/>
  <xsl:template match="/rss/channel">
    <html lang="en">
      <head>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <title><xsl:value-of select="title"/></title>
      </head>
      <body>
        <h1><xsl:value-of select="title"/></h1>
        <p><xsl:value-of select="lastBuildDate"/></p>
        <xsl:for-each select="item">
          <article>
            <h2><a href="{link}"><xsl:value-of select="title"/></a></h2>
            <p><xsl:value-of select="pubDate"/></p>
            <p><xsl:value-of select="description"/></p>
          </article>
        </xsl:for-each>
      </body>
    </html>
  </xsl:template>
</xsl:stylesheet>
"""
