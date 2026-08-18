"""Read-only Streamlit dashboard. Does not scrape, collect, or write to the database."""

from __future__ import annotations

import html
import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import altair as alt
import pandas as pd
import streamlit as st

from app.dashboard_data import (
    dashboard_stats,
    filter_options,
    get_item_detail,
    list_reports,
    read_report_bytes,
    search_items,
)
from app.dashboard_theme import CHART_COLORS, css_for
from app.database.database import session_scope

st.set_page_config(
    page_title="AI Daily Intelligence",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def main() -> None:
    _init_appearance()
    _left, toggle = st.columns([5.1, 1.15])
    with toggle:
        choice = st.radio(
            "Appearance",
            ["Dark", "Light"],
            horizontal=True,
            key="appearance_radio",
            help="Switch the briefing between dark and light.",
        )
    mode = "light" if choice == "Light" else "dark"
    st.session_state.appearance = mode
    st.markdown(f"<style>{css_for(mode)}</style>", unsafe_allow_html=True)
    st.markdown(
        """
        <div class="hero">
          <div class="hero-kicker">Daily briefing desk</div>
          <h1>AI Daily Intelligence</h1>
          <p>Ranked AI news, research, and product moves — read-only view of your local archive.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with session_scope() as session:
        try:
            stats = dashboard_stats(session)
            options = filter_options(session)
        except Exception as exc:  # noqa: BLE001
            st.error("Could not read the local database. Run `python scripts/run_pipeline.py` first.")
            st.caption(str(exc))
            return

    _overview(stats, mode)
    tab_items, tab_reports = st.tabs(["Browse items", "Daily reports"])
    with tab_items:
        _items_tab(options, mode)
    with tab_reports:
        with session_scope() as session:
            reports = list_reports(session)
        _reports_tab(reports)


def _init_appearance() -> None:
    if "appearance_radio" in st.session_state:
        return
    requested = str(st.query_params.get("theme", "dark")).lower()
    st.session_state.appearance_radio = "Light" if requested == "light" else "Dark"


def _overview(stats: dict, mode: str) -> None:
    avg = stats["average_score"]
    colors = CHART_COLORS[mode]
    st.markdown(
        f"""
        <div class="metric-grid">
          {_metric("Articles", stats["articles"], "in archive")}
          {_metric("Scored", stats["scored"], "importance ranked")}
          {_metric("Relevant", stats["relevant"], "passed the filter")}
          {_metric("Avg score", avg if avg is not None else "—", "0–10 weighted")}
          {_metric("Reports", stats["reports"], stats["latest_report_date"] or "none yet")}
        </div>
        """,
        unsafe_allow_html=True,
    )
    if stats["last_run_status"]:
        st.caption(
            f"Last pipeline: **{stats['last_run_status']}** · stage {stats['last_run_stage'] or '—'} · "
            f"latest report {stats['latest_report_date'] or 'none'}"
        )

    left, right = st.columns(2)
    with left:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("**Pipeline mix**")
        _hbar(stats.get("by_status") or {}, colors["status"], mode)
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("**Category mix**")
        _hbar(stats.get("by_category") or {}, colors["category"], mode)
        st.markdown("</div>", unsafe_allow_html=True)


def _items_tab(options: dict, mode: str) -> None:
    st.markdown("##### Filter the briefing")
    query = st.text_input("Search", placeholder="Search title, URL, or text…", label_visibility="collapsed")
    c1, c2, c3, c4 = st.columns(4)
    source = c1.selectbox("Source", ["All"] + options["sources"])
    category = c2.selectbox("Category", ["All"] + options["categories"])
    status = c3.selectbox("Status", ["All"] + options["statuses"])
    kind = c4.selectbox("Kind", ["All"] + options["kinds"])
    f1, f2 = st.columns([3, 1])
    min_score = f1.slider("Minimum score", 0.0, 10.0, 0.0, 0.5)
    relevant_only = f2.checkbox("Relevant only", value=False)

    with session_scope() as session:
        items = search_items(
            session,
            query=query,
            source_name=None if source == "All" else source,
            category=None if category == "All" else category,
            status=None if status == "All" else status,
            item_kind=None if kind == "All" else kind,
            min_score=min_score if min_score > 0 else None,
            relevant_only=relevant_only,
        )

    st.markdown(f"**{len(items)}** matching items")
    if not items:
        st.info("No items match these filters. Run the pipeline first if the database is empty.")
        return

    featured, rest = items[:6], items[6:]
    st.markdown("##### Top matches")
    for item in featured:
        st.markdown(_item_card_html(item), unsafe_allow_html=True)

    table = pd.DataFrame(
        [
            {
                "Score": item["score"] if item["score"] is not None else 0,
                "Title": item["title"],
                "Source": item["source"],
                "Category": item["category"],
                "Status": item["status"],
                "Kind": item["item_kind"],
                "Link": item["url"],
                "id": item["id"],
            }
            for item in items
        ]
    )
    with st.expander(f"Full table ({len(rest) + len(featured)} rows)", expanded=False):
        st.dataframe(
            table.drop(columns=["id"]),
            width="stretch",
            hide_index=True,
            column_config={
                "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=10, format="%.1f"),
                "Link": st.column_config.LinkColumn("Source link"),
                "Title": st.column_config.TextColumn("Title", width="large"),
            },
        )

    selected_id = st.selectbox(
        "Open a briefing card",
        [item["id"] for item in items],
        format_func=lambda item_id: next(
            (
                f"{row['score'] if row['score'] is not None else '—'}  ·  {row['title'][:88]}"
                for row in items
                if row["id"] == item_id
            ),
            str(item_id),
        ),
    )
    with session_scope() as session:
        detail = get_item_detail(session, int(selected_id))
    if detail is None:
        st.warning("Item not found.")
        return

    st.markdown("---")
    col_story, col_score = st.columns([1.45, 1])
    with col_story:
        chips = "".join(_chip(detail.get("category") or "UNCATEGORIZED"))
        chips += "".join(_chip(topic, gold=True) for topic in (detail.get("topics") or [])[:6])
        st.markdown(
            f"""
            <div class="item-card">
              <div class="meta">{html.escape(detail.get("source") or "")} · {html.escape(detail.get("status") or "")}</div>
              <h3>{html.escape(detail["title"])}</h3>
              <div>{chips}</div>
              <p>{html.escape(detail.get("brief") or "No stored summary yet.")}</p>
              <div class="meta"><a href="{html.escape(detail["url"])}" target="_blank">Open original source</a></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if detail.get("abstract"):
            with st.expander("Abstract"):
                st.write(detail["abstract"])
        if detail.get("summary"):
            with st.expander("Stored summary JSON"):
                st.json(detail["summary"])
    with col_score:
        st.markdown("**Why this ranked here**")
        components = detail.get("score_components") or {}
        if components:
            pretty = {
                key.replace("_", " ").title(): value
                for key, value in components.items()
                if key != "weighted_total"
            }
            _hbar(pretty, CHART_COLORS[mode]["score"], mode, x_max=10)
            st.metric("Weighted total", f"{components.get('weighted_total', '—')}")
        else:
            st.caption("This item has not been scored yet.")


def _reports_tab(reports: list[dict]) -> None:
    if not reports:
        st.info("No reports yet. Run `python scripts/generate_report.py` first.")
        return
    for report in reports:
        stats = report.get("stats") or {}
        st.markdown(
            f"""
            <div class="report-card">
              <div class="hero-kicker">Daily packet</div>
              <div class="report-date">{html.escape(str(report["report_date"]))}</div>
              <div class="meta">{html.escape(report.get("title") or "AI Daily Intelligence")} ·
              selected {stats.get("selected", "—")} of {stats.get("candidates", "—")} ·
              {stats.get("flagged", 0)} source-check warning(s)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        buttons = st.columns(3)
        md_bytes = read_report_bytes(report.get("markdown_path"))
        if md_bytes is None and report.get("markdown_content"):
            md_bytes = str(report["markdown_content"]).encode("utf-8")
        html_bytes = read_report_bytes(report.get("html_path"))
        pdf_bytes = read_report_bytes(report.get("pdf_path"))
        if md_bytes:
            buttons[0].download_button(
                "Markdown",
                data=md_bytes,
                file_name=f"ai-daily-intelligence-{report['report_date']}.md",
                mime="text/markdown",
                key=f"md-{report['id']}",
                width="stretch",
            )
        if html_bytes:
            buttons[1].download_button(
                "HTML",
                data=html_bytes,
                file_name=f"ai-daily-intelligence-{report['report_date']}.html",
                mime="text/html",
                key=f"html-{report['id']}",
                width="stretch",
            )
        if pdf_bytes:
            buttons[2].download_button(
                "PDF",
                data=pdf_bytes,
                file_name=f"ai-daily-intelligence-{report['report_date']}.pdf",
                mime="application/pdf",
                key=f"pdf-{report['id']}",
                width="stretch",
            )
        files = report.get("files") or {}
        visual = st.columns(3)
        infographic_bytes = read_report_bytes(files.get("infographic") or stats.get("infographic_path"))
        video_bytes = read_report_bytes(files.get("video") or stats.get("video_path"))
        if infographic_bytes:
            visual[0].download_button(
                "Infographic",
                data=infographic_bytes,
                file_name=f"ai-daily-intelligence-{report['report_date']}-infographic.png",
                mime="image/png",
                key=f"infographic-{report['id']}",
                width="stretch",
            )
            st.image(infographic_bytes, caption="Daily infographic", width="stretch")
        if video_bytes:
            visual[1].download_button(
                "Video (GIF)",
                data=video_bytes,
                file_name=f"ai-daily-intelligence-{report['report_date']}-briefing.gif",
                mime="image/gif",
                key=f"video-{report['id']}",
                width="stretch",
            )
        card_paths = files.get("cards") or stats.get("card_paths") or []
        if card_paths:
            archive = _zip_files(card_paths)
            if archive:
                visual[2].download_button(
                    f"{len(card_paths)} story cards",
                    data=archive,
                    file_name=f"ai-daily-intelligence-{report['report_date']}-cards.zip",
                    mime="application/zip",
                    key=f"cards-{report['id']}",
                    width="stretch",
                )
            thumbs = st.columns(min(4, len(card_paths)))
            for index, path in enumerate(card_paths[:4]):
                payload = read_report_bytes(path)
                if payload:
                    thumbs[index].image(payload, caption=f"Card {index + 1}", width="stretch")
        if report.get("markdown_content"):
            with st.expander("Preview"):
                st.markdown(report["markdown_content"])


def _metric(label: str, value: object, hint: str) -> str:
    return (
        '<div class="metric-card">'
        f'<div class="label">{html.escape(str(label))}</div>'
        f'<div class="value">{html.escape(str(value))}</div>'
        f'<div class="hint">{html.escape(hint)}</div>'
        "</div>"
    )


def _chip(text: str, *, gold: bool = False) -> str:
    klass = "chip gold" if gold else "chip"
    return f'<span class="{klass}">{html.escape(text)}</span>'


def _item_card_html(item: dict) -> str:
    score = item.get("score")
    score_html = f'<span class="score-pill">{score:.1f}</span>' if isinstance(score, (int, float)) else ""
    chips = _chip(item.get("category") or item.get("item_kind") or "item")
    if item.get("relevant"):
        chips += _chip("relevant", gold=True)
    brief = html.escape(item.get("brief") or "No summary stored yet.")
    return f"""
    <div class="item-card">
      {score_html}
      <div class="meta">{html.escape(item.get("source") or "")} · {html.escape(item.get("status") or "")}</div>
      <h3>{html.escape(item.get("title") or "")}</h3>
      <div>{chips}</div>
      <p>{brief}</p>
    </div>
    """


def _hbar(data: dict, color: str, mode: str, x_max: float | None = None) -> None:
    if not data:
        st.caption("Nothing to chart yet.")
        return
    frame = pd.DataFrame({"label": list(data.keys()), "count": list(data.values())})
    x_enc = alt.X("count:Q", title=None)
    if x_max is not None:
        x_enc = alt.X("count:Q", title=None, scale=alt.Scale(domain=[0, x_max]))
    axis = CHART_COLORS[mode]["axis"]
    chart = (
        alt.Chart(frame)
        .mark_bar(cornerRadiusEnd=6, color=color)
        .encode(
            x=x_enc,
            y=alt.Y("label:N", sort="-x", title=None),
            tooltip=["label", "count"],
        )
        .properties(height=max(120, 26 * len(frame)))
        .configure_view(strokeWidth=0)
        .configure_axis(grid=False, domain=False, labelColor=axis, tickColor=axis)
    )
    st.altair_chart(chart, width="stretch")


def _zip_files(paths: list[str]) -> bytes | None:
    buf = io.BytesIO()
    wrote = 0
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for raw in paths:
            path = Path(raw)
            if not path.is_file():
                continue
            archive.write(path, path.name)
            wrote += 1
    if wrote == 0:
        return None
    return buf.getvalue()


if __name__ == "__main__":
    main()
