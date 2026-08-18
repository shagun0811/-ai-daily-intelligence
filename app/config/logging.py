"""Structured logging with pipeline stage prefixes."""

from __future__ import annotations

import logging
import sys
from typing import Any

STAGE_COLLECT = "COLLECT"
STAGE_EXTRACT = "EXTRACT"
STAGE_CLEAN = "CLEAN"
STAGE_FILTER = "FILTER"
STAGE_DEDUP = "DEDUP"
STAGE_EMBED = "EMBED"
STAGE_CLASSIFY = "CLASSIFY"
STAGE_SCORE = "SCORE"
STAGE_SUMMARIZE = "SUMMARIZE"
STAGE_VALIDATE = "VALIDATE"
STAGE_RANK = "RANK"
STAGE_REPORT = "REPORT"
STAGE_SCHEDULE = "SCHEDULE"
STAGE_DB = "DB"
STAGE_CONFIG = "CONFIG"


_CONFIGURED = False

_SECRET_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "token",
        "password",
        "secret",
        "authorization",
        "openai_api_key",
        "anthropic_api_key",
        "gemini_api_key",
    }
)


def setup_logging(level: str | None = None) -> None:
    """Configure root logging once. Never logs secret values."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    from app.config.settings import get_settings

    resolved = (level or get_settings().log_level).upper()
    logging.basicConfig(
        level=resolved,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_stage(
    logger: logging.Logger,
    stage: str,
    message: str,
    *args: Any,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Log a stage-prefixed message. Keyword fields are appended as key=value."""
    safe_fields = {k: v for k, v in fields.items() if k.lower() not in _SECRET_KEYS}
    suffix = ""
    if safe_fields:
        rendered = " ".join(f"{key}={value}" for key, value in safe_fields.items())
        suffix = f" {rendered}"
    logger.log(level, "[%s] " + message + suffix, stage, *args)


def reset_logging_for_tests() -> None:
    global _CONFIGURED
    _CONFIGURED = False
