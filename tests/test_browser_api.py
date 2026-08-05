from datetime import date
import json

import pytest

from kkday_scraper.browser_api import (
    ApiSchemaError,
    BrowserApiClient,
    SessionBlockedError,
    SessionExpiredError,
)


class FakePage:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def evaluate(self, script: str, args: dict) -> dict:
        self.calls.append((script, args))
        return self.responses.pop(0)


def json_response(payload: dict, status: int = 200) -> dict:
    return {
        "status": status,
        "contentType": "application/json;charset=utf-8",
        "text": json.dumps(payload),
    }


def test_fetch_items_data_uses_verified_browser_query_shape() -> None:
    page = FakePage(
        [json_response({"status": 200, "message": "success", "data": {"221992": {}}})]
    )
    client = BrowserApiClient(page, market="zh-tw", timeout_ms=30_000)

    client.fetch_items_data(
        package_id="476215",
        item_ids=("221992",),
        begin_date=date(2026, 7, 22),
        end_date=date(2026, 8, 31),
    )

    script, args = page.calls[0]
    assert "pkgOid=476215" in args["path"]
    assert "itemOidList=221992" in args["path"]
    assert "itemOidList%5B%5D=221992" in args["path"]
    assert "shouldInstantCalendar=false" in args["path"]
    assert args == {
        "path": args["path"],
        "market": "zh-tw",
        "timeoutMs": 30_000,
    }
    assert 'credentials: "include"' in script
    assert "headers: { market }" in script


def test_html_response_stops_as_session_block() -> None:
    page = FakePage(
        [{"status": 200, "contentType": "text/html", "text": "challenge"}]
    )
    client = BrowserApiClient(page, market="zh-tw", timeout_ms=30_000)

    with pytest.raises(SessionBlockedError):
        client.get_json("/api/_nuxt/product/fetch-product-setting?prodMid=149025")


def test_401_stops_as_expired_session() -> None:
    page = FakePage(
        [{"status": 401, "contentType": "application/json", "text": "{}"}]
    )
    client = BrowserApiClient(page, market="zh-tw", timeout_ms=30_000)

    with pytest.raises(SessionExpiredError):
        client.get_json("/api/_nuxt/product/fetch-product-setting?prodMid=149025")


def test_http_200_without_success_contract_is_schema_error() -> None:
    page = FakePage([json_response({"message": "unexpected"})])
    client = BrowserApiClient(page, market="zh-tw", timeout_ms=30_000)

    with pytest.raises(ApiSchemaError):
        client.get_json("/api/_nuxt/product/fetch-product-setting?prodMid=149025")
