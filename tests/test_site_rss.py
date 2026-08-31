"""Outbound RSS 2.0 / Atom feed tests. No network."""

from __future__ import annotations

from xml.etree import ElementTree as ET

from app.site_rss import FEED_DAYS, PUBLIC_SITE_URL, XSL_PATH, build_atom, build_rss, write_public_feeds


_ATOM = "{http://www.w3.org/2005/Atom}"
_GNEWS = (
    "https://news.google.com/rss/articles/CBMiqgFBVV95cUxNSUZaaFh6b0drV2JuR0ZjcVpCY182WnUt"
    "RDJXRG5sOEczWXZLUGlLZVRTdC1zdTYyd0lOYTBMRkFpMWdyX2UwM09OVEJYSHBEWmJucG9tNnRWZDFz"
    "ZF9Uc1JPMGk1WWNCZjVkMGJheDRVNXFNNS1fbjQxX1hpdGNpa0U1QWdsU0MyaUpsRzd4Vkd6d1hqRThP"
    "ZE8zdXhaS01Da1I4Y3Fab1JLUQ?oc=5"
)


def _report(
    day: str,
    title: str,
    why: str,
    url: str,
    source: str = "OpenAI News",
    **extra: str,
) -> dict:
    item = {
        "title": title,
        "summary": why,
        "why_it_matters": why,
        "source_name": source,
        "source_url": url,
        "published_at": day,
    }
    item.update(extra)
    return {
        "report_date": day,
        "title": "AI Daily Intelligence",
        "preview": why,
        "briefing": {
            "title": "AI Daily Intelligence",
            "lede": why,
            "executive": [item],
            "sections": [],
        },
    }


def _items(xml: str):
    root = ET.fromstring(xml)
    channel = root.find("channel")
    assert channel is not None
    return root, channel, channel.findall("item")


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
    assert "Jalapeño’s first results" in (edition.findtext("description") or "")
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


def test_rss_includes_stylesheet_and_stays_well_formed() -> None:
    xml = build_rss(
        [
            _report(
                "2026-08-31",
                "OpenAI wants California to strengthen its newly passed AI safety law",
                "The company is asking the state to tighten SB 53.",
                "https://www.theverge.com/example",
            )
        ]
    )
    assert xml.splitlines()[0] == '<?xml version="1.0" encoding="UTF-8"?>'
    assert f'<?xml-stylesheet type="text/xsl" href="{XSL_PATH}"?>' in xml
    root, channel, items = _items(xml)
    assert root.tag == "rss"
    assert root.attrib["version"] == "2.0"
    assert channel.find("title") is not None
    assert len(items) == 2


def test_rss_never_emits_not_stated_placeholder() -> None:
    xml = build_rss(
        [
            _report(
                "2026-08-19",
                "ScarfBench: Benchmarking AI Agents for Enterprise Java Framework Migration",
                "Not stated in the source.",
                "https://huggingface.co/blog/ibm-research/scarfbench",
                source="Hugging Face Blog",
            )
        ]
    )
    assert "Not stated in the source" not in xml
    _, _, items = _items(xml)
    story = items[1]
    body = story.findtext("description") or ""
    assert "ScarfBench" in body
    assert "Hugging Face Blog" in body


def test_rss_edition_description_keeps_full_headlines() -> None:
    title = "OpenAI wants California to strengthen its newly passed AI safety law"
    xml = build_rss(
        [
            _report(
                "2026-08-31",
                title,
                "OpenAI wants California to strengthen its newly passed AI",
                "https://www.theverge.com/example",
            )
        ]
    )
    _, _, items = _items(xml)
    edition = items[0].findtext("description") or ""
    assert "safety law" in edition
    assert title in edition
    assert not edition.rstrip().endswith(" AI")


def test_rss_trims_mid_word_ellipsis_to_a_complete_phrase() -> None:
    xml = build_rss(
        [
            _report(
                "2026-08-27",
                "OpenAI subpoenaed by Alabama AG over Hugging Face hack",
                "Alabama's attorney general issued a subpoena to OpenAI on Monday. The investigation seeks to determine whether safety practices pose a risk to citizens, the AG's office said in a st…",
                "https://www.theverge.com/example",
                source="The Verge AI",
            )
        ]
    )
    _, _, items = _items(xml)
    body = items[1].findtext("description") or ""
    assert "st…" not in body
    assert "said in a st" not in body
    assert "Monday." in body


def test_rss_prefers_canonical_url_over_google_news() -> None:
    xml = build_rss(
        [
            _report(
                "2026-08-27",
                "Google unveils agentic AI platform for lawyers called Gemini Enterprise for Legal - ABA Journal",
                "Google launched Gemini Enterprise for Legal.",
                _GNEWS,
                source="Google News AI",
                canonical_url="https://www.abajournal.com/web/article/gemini-enterprise-for-legal",
            )
        ]
    )
    _, _, items = _items(xml)
    story = items[1]
    assert story.findtext("link") == "https://www.abajournal.com/web/article/gemini-enterprise-for-legal"
    body = story.findtext("description") or ""
    assert "news.google.com" not in body
    assert "abajournal.com" in body


def test_rss_keeps_google_news_link_but_hides_it_from_description() -> None:
    xml = build_rss(
        [
            _report(
                "2026-08-18",
                "OpenAI launches ChatGPT for Teens",
                "A dedicated ChatGPT mode for teenagers.",
                _GNEWS,
                source="Google News AI",
            )
        ]
    )
    _, _, items = _items(xml)
    story = items[1]
    assert (story.findtext("link") or "").startswith("https://news.google.com/")
    body = story.findtext("description") or ""
    assert "news.google.com" not in body
    assert "Google News AI" in body
    assert "A dedicated ChatGPT mode" in body


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
    xsl = (tmp_path / "feed.xsl").read_text(encoding="utf-8")
    assert feed == alias
    assert feed.startswith("<?xml")
    assert f'href="{XSL_PATH}"' in feed
    assert "<rss version=\"2.0\"" in feed
    assert atom.startswith("<?xml")
    assert "http://www.w3.org/2005/Atom" in atom
    assert xsl.strip().startswith("<?xml")
    assert "xsl:stylesheet" in xsl
    assert "xsl:for-each select=\"item\"" in xsl
    ET.fromstring(feed)
    ET.fromstring(atom)


def test_feed_headers_allow_browser_stylesheet() -> None:
    from pathlib import Path

    from app.config.settings import PROJECT_ROOT

    text = (PROJECT_ROOT / "site" / "_headers").read_text(encoding="utf-8")
    assert "/feed.xml" in text
    assert "/feed.xsl" in text
    assert "text/xsl" in text
    assert "application/xml" in text or "application/rss+xml" in text
    assert "application/rss+xml" in text or "xml" in text
