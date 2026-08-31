from datetime import date, datetime, timezone

import pytest

from kkday_scraper.dates import business_today, default_usage_date, resolve_usage_date


def test_business_date_uses_shanghai_timezone_at_the_utc_day_boundary() -> None:
    before_midnight = datetime(2026, 8, 30, 15, 59, tzinfo=timezone.utc)
    after_midnight = datetime(2026, 8, 30, 16, 0, tzinfo=timezone.utc)

    assert business_today(before_midnight) == date(2026, 8, 30)
    assert default_usage_date(before_midnight) == date(2026, 8, 31)
    assert business_today(after_midnight) == date(2026, 8, 31)
    assert default_usage_date(after_midnight) == date(2026, 9, 1)


def test_resolve_usage_date_keeps_an_explicit_date_unchanged() -> None:
    assert resolve_usage_date("2026-08-31") == date(2026, 8, 31)


def test_resolve_usage_date_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="日期必须是 YYYY-MM-DD"):
        resolve_usage_date("2026/08/31")