import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from kkday_scraper.models import InputItem, PackageRef, PriceStatus
from kkday_scraper.sku_parser import (
    SchemaDriftError,
    package_minimum,
    parse_item_payload,
    validate_package_minimum,
)


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parser_expands_options_and_excludes_closed_sku_from_available_set() -> None:
    rows = parse_item_payload(
        payload=load_fixture("items_data_476215.json"),
        input_item=InputItem(url="https://www.kkday.com/zh-tw/product/149025-example"),
        product_id="149025",
        product_name="日本 eSIM",
        package=PackageRef("476215", "每日/无限流量", ("221992",)),
        item_id="221992",
        usage_date=date(2026, 7, 22),
        currency="KRW",
    )

    assert len(rows) == 2
    assert rows[0].options == ("500MB/日", "1 日")
    assert rows[0].available is True
    assert rows[0].sale_price == Decimal("711")
    assert rows[0].price_status is PriceStatus.TRUSTED
    assert rows[1].available is False
    assert rows[1].price_status is PriceStatus.UNAVAILABLE


def test_parser_never_replaces_sale_price_with_official_price() -> None:
    rows = parse_item_payload(
        payload=load_fixture("items_data_1982144.json"),
        input_item=InputItem(url="https://www.kkday.com/zh-tw/product/149025-example"),
        product_id="149025",
        product_name="日本 eSIM",
        package=PackageRef("1982144", "总量", ("1727921",)),
        item_id="1727921",
        usage_date=date(2026, 7, 22),
        currency="KRW",
    )

    assert rows[0].sale_price == Decimal("10741")
    assert rows[0].official_price == Decimal("21483")


def test_package_minimum_matches_available_sku_minimum() -> None:
    calendar = load_fixture("package_calendar_149025.json")
    rows = parse_item_payload(
        payload=load_fixture("items_data_476215.json"),
        input_item=InputItem(url="https://www.kkday.com/zh-tw/product/149025-example"),
        product_id="149025",
        product_name="日本 eSIM",
        package=PackageRef("476215", "每日/无限流量", ("221992",)),
        item_id="221992",
        usage_date=date(2026, 7, 22),
        currency="KRW",
    )

    expected = package_minimum(calendar, "476215", date(2026, 7, 22))
    assert validate_package_minimum(rows, expected) == (True, "")


def test_unknown_dynamic_price_schema_fails_closed() -> None:
    payload = load_fixture("items_data_1982144.json")
    payload["data"]["1727921"]["skusPriceCalendar"] = {"unknown": {"shape": 1}}

    with pytest.raises(SchemaDriftError, match="skusPriceCalendar"):
        parse_item_payload(
            payload=payload,
            input_item=InputItem(url="https://www.kkday.com/zh-tw/product/149025-example"),
            product_id="149025",
            product_name="日本 eSIM",
            package=PackageRef("1982144", "总量", ("1727921",)),
            item_id="1727921",
            usage_date=date(2026, 7, 22),
            currency="KRW",
        )
