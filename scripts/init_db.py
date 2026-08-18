"""Create SQLite tables and seed sources/topics from YAML."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select

from app.config.logging import STAGE_DB, get_logger, log_stage, setup_logging
from app.config.settings import get_settings
from app.database.database import get_engine, init_db, session_scope
from app.database.models import Source, Topic


def main() -> None:
    setup_logging()
    logger = get_logger("scripts.init_db")
    settings = get_settings()
    init_db(seed=True)
    engine = get_engine()
    with session_scope() as session:
        source_count = session.scalar(select(func.count()).select_from(Source)) or 0
        enabled_count = (
            session.scalar(select(func.count()).select_from(Source).where(Source.enabled.is_(True)))
            or 0
        )
        topic_count = session.scalar(select(func.count()).select_from(Topic)) or 0
    log_stage(
        logger,
        STAGE_DB,
        "database ready url=%s sources=%s enabled=%s topics=%s",
        engine.url.render_as_string(hide_password=True),
        source_count,
        enabled_count,
        topic_count,
    )
    print("Database initialized.")
    print(f"  url:     {settings.resolved_database_url()}")
    print(f"  sources: {source_count} ({enabled_count} enabled)")
    print(f"  topics:  {topic_count}")
    print("Collect with: python scripts/test_collection.py")


if __name__ == "__main__":
    main()
