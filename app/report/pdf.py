"""PDF daily report via ReportLab. Kept short to land near two pages."""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.report.models import DailyReportDocument, ReportItem


def write_pdf(doc: DailyReportDocument, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("ReportTitle", parent=styles["Title"], fontSize=16, spaceAfter=6, leading=20)
    heading = ParagraphStyle("ReportH", parent=styles["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4, leading=15)
    body = ParagraphStyle("ReportBody", parent=styles["Normal"], fontSize=9, leading=12, spaceAfter=4)
    meta = ParagraphStyle("ReportMeta", parent=body, textColor="#444444", fontSize=8)

    story: list = [
        Paragraph(_safe(doc.title), title),
        Paragraph(_safe(f"Date: {doc.report_date.isoformat()}"), meta),
        Paragraph(
            _safe(
                f"Considered {doc.stats.get('candidates', 0)} scored items; "
                f"{doc.stats.get('selected', 0)} in this report; "
                f"{_flagged_phrase(doc.stats.get('flagged', 0))}."
            ),
            meta,
        ),
        Spacer(1, 0.08 * inch),
        Paragraph("Executive Summary", heading),
    ]
    if not doc.executive:
        story.append(Paragraph("No ranked items were available for this cycle.", body))
    for item in doc.executive:
        story.append(
            Paragraph(
                f"<b>{_safe(item.title)}</b> — {_safe(_clip(item.why_it_matters or item.summary, 280))} "
                f'(<link href="{escape(item.source_url)}">{_safe(item.source_name)}</link>)',
                body,
            )
        )

    _pdf_section(story, heading, body, "Top AI Developments", doc.developments, kind="story")
    _pdf_section(story, heading, body, "Research Advancements", doc.research, kind="research")
    _pdf_section(story, heading, body, "Industry & Product Updates", doc.industry, kind="industry")

    story.append(Paragraph("What to Watch", heading))
    if not doc.watch:
        story.append(Paragraph("Nothing flagged beyond the items above.", body))
    for trend in doc.watch:
        story.append(Paragraph(f"• {_safe(trend)}", body))

    story.append(Paragraph("Sources", heading))
    for name, url in doc.sources:
        story.append(
            Paragraph(f'• <link href="{escape(url)}">{_safe(name)}</link> — {_safe(url)}', body)
        )

    document = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title=doc.title,
    )
    document.build(story)


def _pdf_section(story: list, heading, body, title: str, items: list[ReportItem], *, kind: str) -> None:
    item_title = ParagraphStyle("ItemH", parent=body, fontName="Times-Bold")
    story.append(Paragraph(title, heading))
    if not items:
        story.append(Paragraph("No items in this section.", body))
        return
    for item in items:
        story.append(Paragraph(_safe(item.title), item_title))
        if kind == "research":
            if item.problem:
                story.append(Paragraph(f"<b>Problem:</b> {_safe(_clip(item.problem, 280))}", body))
            if item.key_contribution:
                story.append(Paragraph(f"<b>Key contribution:</b> {_safe(_clip(item.key_contribution, 280))}", body))
        else:
            story.append(Paragraph(_safe(_clip(item.summary, 360)), body))
        if item.why_it_matters:
            story.append(Paragraph(f"<b>Why it matters:</b> {_safe(_clip(item.why_it_matters, 240))}", body))
        story.append(
            Paragraph(
                f'<b>Source:</b> <link href="{escape(item.source_url)}">{_safe(item.source_name)}</link>',
                body,
            )
        )
        if item.validation_flags:
            story.append(
                Paragraph(
                    f"<i>Source-check warning:</i> {_safe(', '.join(item.validation_flags))}",
                    body,
                )
            )


def _flagged_phrase(count: object) -> str:
    n = int(count or 0)
    if n == 0:
        return "no source-check warnings"
    label = "source-check warning" if n == 1 else "source-check warnings"
    return f"{n} {label} (a number or quote in the summary was not found in the original article)"


def _safe(text: str) -> str:
    cleaned = (text or "").encode("latin-1", "replace").decode("latin-1")
    return escape(cleaned)


def _clip(text: str, limit: int) -> str:
    body = " ".join((text or "").split())
    if len(body) <= limit:
        return body
    return body[: limit - 1].rstrip() + "..."
