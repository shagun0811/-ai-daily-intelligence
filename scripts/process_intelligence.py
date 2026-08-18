"""Classify, tag topics, and score collected articles. Does not call an LLM."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.logging import setup_logging
from app.database.database import init_db, session_scope
from app.processors.intelligence import IntelligenceProcessor


def main() -> None:
    setup_logging()
    init_db(seed=True)
    with session_scope() as session:
        summary = IntelligenceProcessor(session).run()
    print(summary.as_text())
    print("Phase 4 complete. Run scripts/summarize.py for Phase 5.")


if __name__ == "__main__":
    main()
