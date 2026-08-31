from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


# KKday operations in this project follow the China Standard Time business day,
# regardless of the host machine's configured timezone.
BUSINESS_TIMEZONE = ZoneInfo("Asia/Shanghai")


def business_today(now: datetime | None = None) -> date:
    """Return the current calendar date in the scraper's business timezone."""
    current = now or datetime.now(BUSINESS_TIMEZONE)
    if current.tzinfo is None:
        current = current.replace(tzinfo=BUSINESS_TIMEZONE)
    else:
        current = current.astimezone(BUSINESS_TIMEZONE)
    return current.date()


def default_usage_date(now: datetime | None = None) -> date:
    """Default to the next natural day in the business timezone."""
    return business_today(now) + timedelta(days=1)


def resolve_usage_date(value: str | None, *, now: datetime | None = None) -> date:
    """Parse an explicit YYYY-MM-DD, or resolve the runtime business default."""
    if value is None:
        return default_usage_date(now)
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("日期必须是 YYYY-MM-DD") from exc
