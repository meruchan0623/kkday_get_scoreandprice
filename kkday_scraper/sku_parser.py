from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from .models import InputItem, PackageRef, PriceStatus, SkuRow


class SchemaDriftError(ValueError):
    """The response shape is not one whose price semantics we verified."""


def as_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def package_minimum(
    calendar_payload: dict[str, Any], package_id: str, usage_date: date
) -> Decimal | None:
    value = (
        calendar_payload.get("data", {})
        .get("packages", {})
        .get(str(package_id), {})
        .get("calendar", {})
        .get(usage_date.isoformat(), {})
        .get("min_price")
    )
    return as_decimal(value)


def _spec_name_maps(item: dict[str, Any]) -> dict[str, dict[str, str]]:
    values: dict[str, dict[str, str]] = {}
    for spec in item.get("specs", []):
        spec_id = str(spec.get("spec_oid", ""))
        if not spec_id:
            raise SchemaDriftError("specs 中缺少 spec_oid")
        values[spec_id] = {
            str(option.get("spec_item_oid", "")): str(option.get("name", ""))
            for option in spec.get("spec_items", [])
            if option.get("spec_item_oid") is not None
        }
    return values


def parse_item_payload(
    *,
    payload: dict[str, Any],
    input_item: InputItem,
    product_id: str,
    product_name: str,
    package: PackageRef,
    item_id: str,
    usage_date: date,
    currency: str,
    event: str = "fullday",
) -> list[SkuRow]:
    try:
        item_data = payload["data"][str(item_id)]
        item = item_data["item"]
        calendar_day = item_data["calendar"].get(usage_date.isoformat())
    except (KeyError, TypeError) as exc:
        raise SchemaDriftError(
            f"fetch-items-data 缺少 item {item_id} 的必要字段"
        ) from exc

    dynamic = item_data.get("skusPriceCalendar")
    if dynamic not in (None, {}):
        raise SchemaDriftError("发现未验证的非空 skusPriceCalendar，拒绝猜测动态价格")

    skus = item.get("skus")
    if not isinstance(skus, list):
        raise SchemaDriftError(f"item {item_id} 缺少 SKU 列表")

    option_maps = _spec_name_maps(item)
    close_list = item_data.get("closeList") or {}
    day_saleable = bool(
        calendar_day
        and calendar_day.get("is_saleable")
        and not calendar_day.get("is_sold_out")
        and event in (calendar_day.get("events") or [])
    )

    rows: list[SkuRow] = []
    for sku in skus:
        sku_id = str(sku.get("sku_oid", ""))
        if not sku_id:
            raise SchemaDriftError(f"item {item_id} 的 SKU 缺少 sku_oid")

        options: list[str] = []
        for spec_id, option_id in (sku.get("spec") or {}).items():
            option_name = option_maps.get(str(spec_id), {}).get(str(option_id))
            if not option_name:
                raise SchemaDriftError(
                    f"SKU {sku_id} 无法解析规格 {spec_id}={option_id}"
                )
            options.append(option_name)

        closed_events = close_list.get(sku_id, {}).get(
            usage_date.isoformat(), []
        )
        available = day_saleable and event not in closed_events
        sale_price = as_decimal((sku.get("single_price") or {}).get(event))
        official_price = as_decimal(sku.get("official_price"))
        if not available:
            status = PriceStatus.UNAVAILABLE
            note = "所选日期或事件不可售"
        elif sale_price is None:
            status = PriceStatus.MISSING
            note = f"可售 SKU 缺少 single_price.{event}"
        else:
            status = PriceStatus.TRUSTED
            note = ""

        rows.append(
            SkuRow(
                vendor=input_item.vendor,
                input_order=input_item.input_order,
                product_id=product_id,
                product_url=input_item.url,
                product_name=product_name,
                package_id=package.package_id,
                package_name=package.name,
                item_id=str(item_id),
                sku_id=sku_id,
                usage_date=usage_date,
                options=tuple(options),
                available=available,
                currency=currency,
                sale_price=sale_price,
                official_price=official_price,
                price_source=f"single_price.{event}" if sale_price is not None else "",
                price_status=status,
                note=note,
            )
        )
    return rows


def validate_package_minimum(
    rows: list[SkuRow], expected_minimum: Decimal | None
) -> tuple[bool, str]:
    available = [row for row in rows if row.available]
    missing = [row for row in available if row.sale_price is None]
    if missing:
        return False, f"{len(missing)} 个可售 SKU 缺少价格"

    prices = [row.sale_price for row in available if row.sale_price is not None]
    if not prices:
        return expected_minimum is None, "套餐没有可售 SKU"
    actual = min(prices)
    if expected_minimum is None:
        return False, f"价格日历缺少套餐最低价，SKU 最低价为 {actual}"
    if actual != expected_minimum:
        return False, f"SKU 最低价 {actual} 与价格日历最低价 {expected_minimum} 不一致"
    return True, ""
