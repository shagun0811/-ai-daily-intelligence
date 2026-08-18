"""Generate today's Markdown, HTML, and PDF intelligence report. No LLM call."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.logging import setup_logging
from app.database.database import init_db, session_scope
from app.report.generator import ReportGenerator


def main() -> None:
    setup_logging()
    init_db(seed=True)
    with session_scope() as session:
        summary = ReportGenerator(session).run()
    print(summary.as_text())
    print("Phase 6 complete. Run: streamlit run app/dashboard.py")


if __name__ == "__main__":
    main()
