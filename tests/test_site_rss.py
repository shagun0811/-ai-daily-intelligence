"""Outbound RSS 2.0 / Atom feed tests. No network."""

from __future__ import annotations

from xml.etree import ElementTree as ET

from app.site_rss import FEED_DAYS, PUBLIC_SITE_URL, build_atom, build_rss, write_public_feeds


_ATOM = "{http://www.w3.org/2005/Atom}"


def _report(day: str, title: str, why: str, url: str, source: str = "OpenAI News") -> dict:
    return {
        "report_date": day,
        "title": "AI Daily Intelligence",
        "preview": why,
        "briefing": {
            "title": "AI Daily Intelligence",
            "lede": why,
            "executive": [
                {
                    "title": title,
                    "summary": why,
                    "why_it_matters": why,
                    "source_name": source,
                    "source_url": url,
                    "published_at": day,
                }
            ],
            "sections": [],
        },
    }


def test_rss_is_well_formed_with_expected_tags() -> None:
    xml = build_rss(
        [
            _report(
                "2026-08-27",
                "Jalapeño’s first results",
                "Custom inference chip with lower latency.",
                "https://openai.com/index/jalapeno-first-results",
            )
        ]
    )
    root = ET.fromstring(xml)
    assert root.tag == "rss"
    assert root.attrib["version"] == "2.0"
    channel = root.find("channel")
    assert channel is not None
    assert channel.findtext("title") == "AI Daily Intelligence"
    assert channel.findtext("link") == PUBLIC_SITE_URL
    assert channel.findtext("language") == "en"
    assert channel.find("lastBuildDate") is not None
    self_link = channel.find(f"{_ATOM}link")
    assert self_link is not None
    assert self_link.attrib["href"].endswith("/feed.xml")
    assert self_link.attrib["rel"] == "self"
    items = channel.findall("item")
    assert len(items) == 2
    edition, story = items
    assert edition.findtext("title") == "AI Daily Intelligence — 2026-08-27"
    assert edition.findtext("link") == f"{PUBLIC_SITE_URL}/#2026-08-27"
    assert edition.find("guid") is not None
    assert edition.find("pubDate") is not None
    assert "Custom inference chip" in (edition.findtext("description") or "")
    assert story.findtext("title") == "Jalapeño’s first results"
    assert story.findtext("link") == "https://openai.com/index/jalapeno-first-results"
    assert "lower latency" in (story.findtext("description") or "")
    assert story.find("guid") is not None
    assert story.find("guid").attrib.get("isPermaLink") == "false"
    assert story.find("pubDate") is not None
    guids = [item.findtext("guid") for item in items]
    assert len(guids) == len(set(guids))


def test_rss_escapes_ampersand_and_brackets() -> None:
    xml = build_rss(
        [
            _report(
                "2026-08-27",
                "Foo & Bar <Baz>",
                "1 < 2 & 3 > 0",
                "https://example.com/x?a=1&b=2",
                source="A&B",
            )
        ]
    )
    ET.fromstring(xml)
    assert "Foo &amp; Bar &lt;Baz&gt;" in xml
    assert "1 &lt; 2 &amp; 3 &gt; 0" in xml
    assert "a=1&amp;b=2" in xml
    assert "Foo & Bar" not in xml
    assert "<Baz>" not in xml


def test_rss_keeps_last_fourteen_editions() -> None:
    reports = [
        _report(
            f"2026-08-{day:02d}",
            f"Story {day}",
            f"Why {day}",
            f"https://example.com/{day}",
        )
        for day in range(10, 28)
    ]
    xml = build_rss(reports)
    root = ET.fromstring(xml)
    titles = [item.findtext("title") or "" for item in root.find("channel").findall("item")]
    edition_titles = [title for title in titles if title.startswith("AI Daily Intelligence — ")]
    assert len(edition_titles) == FEED_DAYS
    assert edition_titles[0] == "AI Daily Intelligence — 2026-08-27"
    assert edition_titles[-1] == "AI Daily Intelligence — 2026-08-14"
    assert "2026-08-13" not in xml


def test_atom_is_well_formed() -> None:
    xml = build_atom(
        [
            _report(
                "2026-08-27",
                "OpenAI subpoenaed by Alabama AG",
                "Safety investigation after a Hugging Face hack.",
                "https://www.theverge.com/example",
            )
        ]
    )
    root = ET.fromstring(xml)
    assert root.tag == f"{_ATOM}feed"
    assert root.findtext(f"{_ATOM}title") == "AI Daily Intelligence"
    entries = root.findall(f"{_ATOM}entry")
    assert len(entries) == 2
    assert entries[1].findtext(f"{_ATOM}title") == "OpenAI subpoenaed by Alabama AG"


def test_write_public_feeds_duplicates_rss_alias(tmp_path) -> None:
    write_public_feeds(
        tmp_path,
        [
            _report(
                "2026-08-26",
                "Learning never stops",
                "ChatGPT in classrooms.",
                "https://openai.com/index/learning-never-stops",
            )
        ],
    )
    feed = (tmp_path / "feed.xml").read_text(encoding="utf-8")
    alias = (tmp_path / "rss.xml").read_text(encoding="utf-8")
    atom = (tmp_path / "atom.xml").read_text(encoding="utf-8")
    assert feed == alias
    assert feed.startswith("<?xml")
    assert "<rss version=\"2.0\"" in feed
    assert atom.startswith("<?xml")
    assert "http://www.w3.org/2005/Atom" in atom
    ET.fromstring(feed)
    ET.fromstring(atom)
