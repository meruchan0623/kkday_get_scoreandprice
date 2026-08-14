import json
from dataclasses import replace
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
    assert [row.options for row in rows] == [
        ("無限流量（保證不降速）", "1 日"),
        ("500MB/日", "1 日"),
    ]
    assert rows[0].available is False
    assert rows[0].price_status is PriceStatus.UNAVAILABLE
    assert rows[1].available is True
    assert rows[1].sale_price == Decimal("711")
    assert rows[1].price_status is PriceStatus.TRUSTED


def test_parser_ignores_dom_like_display_prices_and_uses_only_api_single_price() -> None:
    payload = load_fixture("items_data_476215.json")
    # These resemble values a page snapshot/DOM might expose.  They are not part
    # of the trusted API schema and must have no influence on the exported SKU.
    payload["pageMinPrice"] = "1"
    payload["data"]["221992"]["item"]["displayPrice"] = "1"
    payload["data"]["221992"]["item"]["domPrice"] = "1"

    rows = parse_item_payload(
        payload=payload,
        input_item=InputItem(url="https://www.kkday.com/zh-tw/product/149025-example"),
        product_id="149025",
        product_name="日本 eSIM",
        package=PackageRef("476215", "每日/无限流量", ("221992",)),
        item_id="221992",
        usage_date=date(2026, 7, 22),
        currency="KRW",
    )

    trusted = [row for row in rows if row.price_status is PriceStatus.TRUSTED]
    assert [row.sale_price for row in trusted] == [Decimal("711")]
    assert all(row.price_source == "single_price.fullday" for row in trusted)


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


def test_parser_sorts_skus_by_website_spec_tree_not_api_array_order() -> None:
    payload = {
        "data": {
            "item-1": {
                "item": {
                    "specs": [
                        {
                            "spec_oid": "traffic",
                            "spec_items": [
                                {"spec_item_oid": "1gb", "name": "1GB"},
                                {"spec_item_oid": "3gb", "name": "3GB"},
                            ],
                        },
                        {
                            "spec_oid": "days",
                            "spec_items": [
                                {"spec_item_oid": "1d", "name": "1 日"},
                                {"spec_item_oid": "3d", "name": "3 日"},
                            ],
                        },
                    ],
                    "skus": [
                        {"sku_oid": "last", "spec": {"traffic": "3gb", "days": "3d"}, "single_price": {"fullday": 40}},
                        {"sku_oid": "first", "spec": {"traffic": "1gb", "days": "1d"}, "single_price": {"fullday": 10}},
                        {"sku_oid": "third", "spec": {"traffic": "3gb", "days": "1d"}, "single_price": {"fullday": 30}},
                        {"sku_oid": "second", "spec": {"traffic": "1gb", "days": "3d"}, "single_price": {"fullday": 20}},
                    ],
                },
                "calendar": {"2026-07-22": {"is_saleable": True, "is_sold_out": False, "events": ["fullday"]}},
                "closeList": {},
                "skusPriceCalendar": {},
            }
        }
    }

    rows = parse_item_payload(
        payload=payload,
        input_item=InputItem(url="https://www.kkday.com/zh-tw/product/1"),
        product_id="1",
        product_name="tree",
        package=PackageRef("pkg", "package", ("item-1",)),
        item_id="item-1",
        usage_date=date(2026, 7, 22),
        currency="TWD",
        package_order=2,
        item_order=3,
    )

    assert [row.sku_id for row in rows] == ["first", "second", "third", "last"]
    assert [row.tree_order for row in rows] == [
        (2, 3, 0, 0),
        (2, 3, 0, 1),
        (2, 3, 1, 0),
        (2, 3, 1, 1),
    ]


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


def test_package_calendar_floor_may_belong_to_closed_sku() -> None:
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
    # The package calendar can expose a lowest display floor for a SKU whose
    # closeList excludes it on the selected date. The trusted sellable price
    # must remain the API single_price of the available SKU.
    rows = [
        replace(rows[0], available=False, sale_price=Decimal("4")),
        replace(rows[1], available=True, sale_price=Decimal("13")),
    ]
    assert validate_package_minimum(rows, Decimal("4")) == (True, "")


def test_package_calendar_floor_absent_from_sku_prices_fails_closed() -> None:
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
    valid, reason = validate_package_minimum(rows, Decimal("999999"))
    assert valid is False
    assert "不存在于套餐 SKU 价格集合" in reason


def test_package_without_sellable_sku_is_not_a_price_mismatch() -> None:
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
    unavailable = [replace(row, available=False) for row in rows]
    assert validate_package_minimum(unavailable, Decimal("4")) == (True, "套餐没有可售 SKU")
