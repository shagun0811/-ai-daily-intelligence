"""Date parsing. Missing or invalid dates become None — never crash a source."""

from __future__ import annotations

from datetime import date, datetime, timezone
from time import struct_time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil import parser as date_parser

ParserError = getattr(date_parser, "ParserError", ValueError)

IST_ZONE_NAME = "Asia/Kolkata"


def today_ist() -> date:
    """Edition calendar day. Always Asia/Kolkata, not the runner's UTC date."""
    try:
        zone = ZoneInfo(IST_ZONE_NAME)
    except ZoneInfoNotFoundError:
        zone = timezone.utc
    return datetime.now(zone).date()


def parse_datetime(value: str | datetime | struct_time | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, struct_time):
        try:
            return datetime(*value[:6], tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = date_parser.parse(text)
    except (ValueError, OverflowError, TypeError, ParserError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
