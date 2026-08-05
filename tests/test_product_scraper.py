import json
from datetime import date
from pathlib import Path

import pytest

from kkday_scraper.browser_api import SessionBlockedError
from kkday_scraper.models import (
    FailureKind,
    InputItem,
    ReadinessReport,
    RunConfig,
    SessionProbe,
)
from kkday_scraper.product_scraper import (
    PAGE_DIAGNOSTIC_SCRIPT,
    ProductScraper,
    extract_product_snapshot,
)


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakePage:
    def __init__(self, snapshot: dict) -> None:
        self.snapshot = snapshot
        self.goto_calls: list[str] = []
        self.url = snapshot["url"]

    def goto(self, url: str, **_kwargs) -> None:
        self.goto_calls.append(url)
        self.url = url

    def wait_for_function(self, _expression: str, **_kwargs) -> None:
        return None

    def evaluate(self, _expression: str) -> dict:
        return self.snapshot


class FakeApi:
    def __init__(self) -> None:
        self.calendar_calls: list[str] = []
        self.item_calls: list[str] = []

    def fetch_package_calendar(self, product_id, _begin, _end) -> dict:
        self.calendar_calls.append(product_id)
        return load_fixture("package_calendar_149025.json")

    def fetch_items_data(self, package_id, _item_ids, _begin, _end) -> dict:
        self.item_calls.append(package_id)
        name = (
            "items_data_476215.json"
            if package_id == "476215"
            else "items_data_1982144.json"
        )
        return load_fixture(name)


def probe(page: FakePage) -> SessionProbe:
    return SessionProbe(True, True, True, "TWD", "zh-tw", page.url)


def test_snapshot_reads_packages_without_clicking() -> None:
    page = FakePage(load_fixture("product_snapshot_149025.json"))
    snapshot = extract_product_snapshot(page, page.url)

    assert snapshot.product_id == "149025"
    assert [package.package_id for package in snapshot.packages] == [
        "476215",
        "1982144",
    ]
    assert snapshot.packages[0].item_ids == ("221992",)


def test_snapshot_falls_back_to_numeric_product_id_from_url() -> None:
    raw = load_fixture("product_snapshot_149025.json")
    raw.pop("productId")
    page = FakePage(raw)

    snapshot = extract_product_snapshot(page, page.url)

    assert snapshot.product_id == "149025"


def test_scrape_calls_each_package_once_and_returns_available_prices(
    tmp_path: Path,
) -> None:
    page = FakePage(load_fixture("product_snapshot_149025.json"))
    api = FakeApi()
    scraper = ProductScraper(
        page, api, sleep=lambda _seconds: None, uniform=lambda low, _high: low
    )
    config = RunConfig(date(2026, 7, 22), tmp_path)

    result = scraper.scrape(InputItem(url=page.url), probe(page), config)

    assert page.goto_calls == [page.url]
    assert api.item_calls == ["476215", "1982144"]
    assert len(result.rows) == 3
    assert len([row for row in result.rows if row.available]) == 2
    assert all(row.sale_price is not None for row in result.rows if row.available)
    assert result.failures == ()


def test_scrape_stops_before_product_requests_when_currency_mismatches(
    tmp_path: Path,
) -> None:
    page = FakePage(load_fixture("product_snapshot_149025.json"))
    api = FakeApi()
    scraper = ProductScraper(page, api)
    config = RunConfig(date(2026, 7, 22), tmp_path, currency="TWD")
    usd_probe = SessionProbe(True, True, True, "USD", "zh-tw", page.url)

    result = scraper.scrape(InputItem(url=page.url), usd_probe, config)

    assert page.goto_calls == []
    assert api.calendar_calls == []
    assert api.item_calls == []
    assert result.rows == ()
    assert result.failures[0].kind.value == "currency_mismatch"
    assert "TWD" in result.failures[0].message
    assert "USD" in result.failures[0].message


def test_scrape_reports_business_readiness_without_duplicate_requests(
    tmp_path: Path,
) -> None:
    page = FakePage(load_fixture("product_snapshot_149025.json"))
    api = FakeApi()
    reports: list[ReadinessReport] = []
    scraper = ProductScraper(
        page,
        api,
        sleep=lambda _seconds: None,
        uniform=lambda low, _high: low,
        readiness_reporter=reports.append,
    )

    scraper.scrape(
        InputItem(url=page.url),
        probe(page),
        RunConfig(date(2026, 7, 22), tmp_path),
    )

    assert [(r.product_page_ready, r.price_calendar_ready, r.sku_api_ready) for r in reports] == [
        (True, None, None),
        (True, True, None),
        (True, True, True),
    ]
    assert api.calendar_calls == ["149025"]
    assert api.item_calls == ["476215", "1982144"]


class FailedProductPage:
    def __init__(self, *, status: int, challenge: bool) -> None:
        self.url = "https://www.kkday.com/zh-tw/product/149025-example"
        self.status = status
        self.challenge = challenge

    def goto(self, url: str, **_kwargs):
        self.url = url
        return type("Response", (), {"status": self.status})()

    def wait_for_function(self, _expression: str, **_kwargs) -> None:
        raise TimeoutError("Nuxt timeout")

    def evaluate(self, _expression: str) -> dict:
        return {
            "url": self.url,
            "readyState": "complete",
            "challenge": self.challenge,
            "hasNuxtPackages": False,
        }


def test_blocked_product_page_reports_calendar_only_and_stops(
    tmp_path: Path,
) -> None:
    page = FailedProductPage(status=403, challenge=True)
    api = FakeApi()
    reports: list[ReadinessReport] = []
    scraper = ProductScraper(page, api, readiness_reporter=reports.append)

    with pytest.raises(SessionBlockedError, match="无法取得 SKU 树"):
        scraper.scrape(
            InputItem(url=page.url),
            SessionProbe(True, True, True, "TWD", "zh-tw", page.url),
            RunConfig(date(2026, 7, 22), tmp_path),
        )

    assert api.calendar_calls == ["149025"]
    assert reports[-1].product_page_ready is False
    assert reports[-1].price_calendar_ready is True
    assert reports[-1].sku_api_ready is None
    assert "无法取得 SKU 树" in (reports[-1].reason or "")


def test_normal_page_without_nuxt_is_schema_failure(tmp_path: Path) -> None:
    page = FailedProductPage(status=200, challenge=False)
    api = FakeApi()
    scraper = ProductScraper(page, api)

    result = scraper.scrape(
        InputItem(url=page.url),
        SessionProbe(True, True, True, "TWD", "zh-tw", page.url),
        RunConfig(date(2026, 7, 22), tmp_path),
    )

    assert result.failures[0].kind is FailureKind.SCHEMA
    assert api.calendar_calls == []


def test_challenge_detection_does_not_match_generic_verification_copy() -> None:
    assert "|驗證/" not in PAGE_DIAGNOSTIC_SCRIPT
    assert "安全驗證" in PAGE_DIAGNOSTIC_SCRIPT


def test_blocked_page_calendar_diagnostic_is_attempted_only_once(
    tmp_path: Path,
) -> None:
    page = FailedProductPage(status=403, challenge=True)

    class FailingDiagnosticApi(FakeApi):
        def fetch_package_calendar(self, product_id, _begin, _end):
            from kkday_scraper.browser_api import BrowserApiError

            self.calendar_calls.append(product_id)
            raise BrowserApiError("temporary")

    api = FailingDiagnosticApi()
    sleeps: list[float] = []
    scraper = ProductScraper(page, api, sleep=sleeps.append)

    with pytest.raises(SessionBlockedError):
        scraper.scrape(
            InputItem(url=page.url),
            SessionProbe(True, True, True, "TWD", "zh-tw", page.url),
            RunConfig(date(2026, 7, 22), tmp_path),
        )

    assert api.calendar_calls == ["149025"]
    assert sleeps == []


def test_scrape_retries_transient_api_failure_once(tmp_path: Path) -> None:
    page = FakePage(load_fixture("product_snapshot_149025.json"))
    api = FakeApi()
    real_fetch = api.fetch_package_calendar
    calls = 0

    def flaky(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            from kkday_scraper.browser_api import BrowserApiError

            raise BrowserApiError("temporary")
        return real_fetch(*args)

    api.fetch_package_calendar = flaky
    sleeps: list[float] = []
    scraper = ProductScraper(page, api, sleep=sleeps.append)
    config = RunConfig(date(2026, 7, 22), tmp_path)

    result = scraper.scrape(InputItem(url=page.url), probe(page), config)

    assert calls == 2
    assert sleeps[0] == 1.0
    assert result.failures == ()


def test_scrape_does_not_retry_schema_contract_failure(tmp_path: Path) -> None:
    page = FakePage(load_fixture("product_snapshot_149025.json"))
    api = FakeApi()
    calls = 0

    def invalid_calendar(*_args):
        nonlocal calls
        calls += 1
        from kkday_scraper.browser_api import ApiSchemaError

        raise ApiSchemaError("schema")

    api.fetch_package_calendar = invalid_calendar
    sleeps: list[float] = []
    scraper = ProductScraper(page, api, sleep=sleeps.append)
    config = RunConfig(date(2026, 7, 22), tmp_path)

    result = scraper.scrape(InputItem(url=page.url), probe(page), config)

    assert calls == 1
    assert sleeps == []
    assert result.failures[0].retryable is False


def test_scrape_stop_gate_prevents_next_package_request(tmp_path: Path) -> None:
    page = FakePage(load_fixture("product_snapshot_149025.json"))
    api = FakeApi()
    checks = iter((True, True, True, False))
    scraper = ProductScraper(
        page,
        api,
        sleep=lambda _seconds: None,
        uniform=lambda low, _high: low,
        continue_run=lambda: next(checks),
    )
    config = RunConfig(date(2026, 7, 22), tmp_path)

    result = scraper.scrape(InputItem(url=page.url), probe(page), config)

    assert api.item_calls == ["476215"]
    assert len(result.rows) == 2
    assert result.warnings[-1] == "用户在套餐之间停止"
