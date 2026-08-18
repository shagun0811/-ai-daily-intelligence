"""Run the daily pipeline now, or start the local APScheduler daemon."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.logging import setup_logging
from app.config.settings import get_settings
from app.scheduler.service import run_job, start_scheduler


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Daily Intelligence scheduler")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run the pipeline once now and exit. Does not require SCHEDULER_ENABLED.",
    )
    args = parser.parse_args()
    setup_logging()

    if args.once:
        outcome = run_job()
        print(outcome.as_text())
        sys.exit(0 if outcome.ok else 1)

    settings = get_settings()
    if not settings.scheduler_enabled:
        print(
            "SCHEDULER_ENABLED is false.\n"
            "To run once:  python scripts/run_scheduler.py --once\n"
            "To run daily: set SCHEDULER_ENABLED=true in .env, then run this script again."
        )
        sys.exit(2)

    print(
        f"Scheduler on — daily at {settings.scheduler_hour:02d}:{settings.scheduler_minute:02d} "
        f"{settings.scheduler_timezone}. Ctrl+C to stop."
    )
    start_scheduler()


if __name__ == "__main__":
    main()
