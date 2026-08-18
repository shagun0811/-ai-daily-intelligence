"""APScheduler wiring. Does not run unless SCHEDULER_ENABLED=true or --once."""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config.logging import STAGE_SCHEDULE, get_logger, log_stage, setup_logging
from app.config.settings import get_settings
from app.pipeline.runner import PipelineOutcome, run_daily_pipeline
from app.scheduler.lock import OverlapError, PipelineLock

logger = get_logger(__name__)


def resolve_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        log_stage(logger, STAGE_SCHEDULE, "unknown timezone=%s falling back to UTC", name, level=30)
        return ZoneInfo("UTC")


def cron_trigger(*, hour: int, minute: int, timezone: str) -> CronTrigger:
    return CronTrigger(hour=hour, minute=minute, timezone=resolve_timezone(timezone))


def run_job() -> PipelineOutcome:
    """One guarded pipeline execution."""
    setup_logging()
    try:
        with PipelineLock():
            log_stage(logger, STAGE_SCHEDULE, "starting daily job")
            outcome = run_daily_pipeline()
            log_stage(
                logger,
                STAGE_SCHEDULE,
                "daily job finished ok=%s errors=%s",
                outcome.ok,
                len(outcome.errors),
            )
            return outcome
    except OverlapError as exc:
        log_stage(logger, STAGE_SCHEDULE, "skipped overlap: %s", exc, level=30)
        outcome = PipelineOutcome(errors=[str(exc)])
        return outcome


def build_scheduler() -> BlockingScheduler:
    settings = get_settings()
    zone = resolve_timezone(settings.scheduler_timezone)
    scheduler = BlockingScheduler(timezone=zone)
    trigger = cron_trigger(
        hour=settings.scheduler_hour,
        minute=settings.scheduler_minute,
        timezone=settings.scheduler_timezone,
    )
    scheduler.add_job(run_job, trigger=trigger, id="daily_pipeline", replace_existing=True)
    log_stage(
        logger,
        STAGE_SCHEDULE,
        "job registered hour=%s minute=%s tz=%s",
        settings.scheduler_hour,
        settings.scheduler_minute,
        settings.scheduler_timezone,
    )
    return scheduler


def start_scheduler() -> None:
    settings = get_settings()
    if not settings.scheduler_enabled:
        raise RuntimeError(
            "SCHEDULER_ENABLED is false. Set SCHEDULER_ENABLED=true in .env "
            "or run: python scripts/run_scheduler.py --once"
        )
    scheduler = build_scheduler()
    log_stage(logger, STAGE_SCHEDULE, "blocking scheduler starting")
    scheduler.start()
