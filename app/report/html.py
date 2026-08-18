"""HTML daily report via Jinja2."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.report.models import DailyReportDocument

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def render_html(doc: DailyReportDocument) -> str:
    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template("daily.html.j2")
    return template.render(doc=doc)
