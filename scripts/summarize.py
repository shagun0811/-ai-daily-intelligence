"""Summarize scored articles with the configured LLM provider (default: mock)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.logging import setup_logging
from app.database.database import init_db, session_scope
from app.processors.summarizer import Summarizer


def main() -> None:
    setup_logging()
    init_db(seed=True)
    with session_scope() as session:
        summary = Summarizer(session).run()
    print(summary.as_text())
    print("Phase 5 complete. Run scripts/generate_report.py for Phase 6.")


if __name__ == "__main__":
    main()
