"""Collect enabled sources into SQLite. Does not classify or summarize."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.collectors.source_manager import SourceManager
from app.config.logging import setup_logging
from app.database.database import init_db, session_scope


def main() -> None:
    setup_logging()
    init_db(seed=True)
    with session_scope() as session:
        summary = SourceManager(session).run(enabled_only=True)
    print(summary.as_text())
    print("Phase 2 collection complete. Cleaning and dedup start in Phase 3.")


if __name__ == "__main__":
    main()
