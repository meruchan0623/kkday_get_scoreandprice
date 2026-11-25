from datetime import date
import subprocess
import json

import pytest

from kkday_scraper.browser_api import (
    ApiSchemaError,
    BrowserApiClient,
    ORIGINAL_PACKAGES_DATA_SCRIPT,
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


def test_fetch_packages_data_reuses_only_a_verified_public_performance_url() -> None:
    page = FakePage(
        [json_response({"message": "success", "data": {"PACKAGE": {}, "ITEM": {}}})]
    )
    client = BrowserApiClient(page, market="zh-tw", timeout_ms=30_000)

    client.fetch_packages_data("135034", date(2026, 11, 26), date(2026, 11, 26))

    script, args = page.calls[0]
    assert args == {"expectedProdMid": "135034", "market": "zh-tw", "timeoutMs": 30_000}
    assert "performance.getEntriesByType" in script
    assert 'url.searchParams.get("prodMid") !== expectedProdMid' in script
    assert "token|auth|cookie|session|signature|secret|key" in script
    assert 'key === "previewToken" && value === ""' in script


def test_fetch_packages_data_fails_closed_without_a_verified_original_request() -> None:
    page = FakePage([{"source": "not_found"}])
    client = BrowserApiClient(page, market="zh-tw", timeout_ms=30_000)

    with pytest.raises(ApiSchemaError, match="未发现已验证"):
        client.fetch_packages_data("135034", date(2026, 11, 26), date(2026, 11, 26))


def test_original_packages_request_uses_only_matching_public_performance_url() -> None:
    runner = """
const fs = require('fs');
const script = fs.readFileSync(0, 'utf8');
const calls = [];
global.location = {origin: 'https://www.kkday.com'};
global.performance = {getEntriesByType: () => [
  {name: 'https://www.kkday.com/api/_nuxt/product/fetch-packages-data?prodMid=other'},
  {name: 'https://elsewhere.invalid/api/_nuxt/product/fetch-packages-data?prodMid=135034'},
  {name: 'https://www.kkday.com/api/_nuxt/product/fetch-packages-data?prodMid=135034&previewToken&platform=WEB'}
]};
global.fetch = async (path) => {
  calls.push(path);
  return {status: 200, headers: {get: () => 'application/json'}, text: async () => '{"message":"success","data":{}}'};
};
;(async () => {
  const result = await eval(`(${script})`)({expectedProdMid: '135034', market: 'zh-tw', timeoutMs: 500});
  process.stdout.write(JSON.stringify({result, calls}));
})().catch((error) => { console.error(error); process.exit(1); });
"""
    completed = subprocess.run(
        ["node", "-e", runner],
        input=ORIGINAL_PACKAGES_DATA_SCRIPT,
        text=True,
        capture_output=True,
        check=True,
    )
    result = json.loads(completed.stdout)

    assert result["calls"] == [
        "/api/_nuxt/product/fetch-packages-data?prodMid=135034&previewToken&platform=WEB"
    ]
    assert result["result"]["source"] == "performance"


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
