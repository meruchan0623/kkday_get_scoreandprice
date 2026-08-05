from __future__ import annotations

import re
from dataclasses import replace
from datetime import timedelta
from random import uniform
from time import sleep
from typing import Callable, Protocol

from .browser_api import (
    ApiSchemaError,
    BrowserApiClient,
    BrowserApiError,
    SessionBlockedError,
    SessionExpiredError,
)
from .models import (
    FailureKind,
    FailureRecord,
    InputItem,
    PackageRef,
    PriceStatus,
    ProductResult,
    ProductSnapshot,
    ReadinessReport,
    RunConfig,
    SessionProbe,
)
from .sku_parser import (
    SchemaDriftError,
    package_minimum,
    parse_item_payload,
    validate_package_minimum,
)


SNAPSHOT_SCRIPT = r"""
() => {
  const option = window.__NUXT__ && window.__NUXT__.pinia && window.__NUXT__.pinia["option-section"];
  if (!option || !option.packages) return null;
  const match = location.pathname.match(/\/product\/(\d+)/);
  const productId = String((option.productSetting && option.productSetting.prod_mid) || (match && match[1]) || "");
  const title =
    (option.product && (option.product.name || option.product.title)) ||
    (option.prodInfo && (option.prodInfo.name || option.prodInfo.title)) ||
    (document.querySelector("h1") && document.querySelector("h1").textContent.trim()) ||
    document.title.replace(/\s*-\s*KKday\s*$/, "");
  return {
    productId,
    url: location.href,
    name: String(title || ""),
    packages: Object.values(option.packages).map(pkg => ({
      packageId: String(pkg.pkg_oid),
      name: String(pkg.name || ""),
      itemIds: (pkg.items || []).map(value => String(value)),
      description: Array.isArray(pkg.description_module)
        ? pkg.description_module.map(value => String(value.text || "")).filter(Boolean).join(" | ")
        : ""
    }))
  };
}
"""


class PageLike(Protocol):
    url: str

    def goto(self, url: str, **kwargs) -> object: ...

    def wait_for_function(self, expression: str, **kwargs) -> None: ...

    def evaluate(self, expression: str) -> dict | None: ...


PAGE_DIAGNOSTIC_SCRIPT = r"""
() => {
  const text = String(document.body && document.body.innerText || "")
    .slice(0, 5000)
    .toLowerCase();
  return {
    url: location.href,
    readyState: document.readyState,
    challenge: /datadome|captcha|verify you are human|access denied|存取遭拒|安全驗證|安全验证|機器人驗證|机器人验证/.test(text),
    hasNuxtPackages: Boolean(window.__NUXT__?.pinia?.["option-section"]?.packages)
  };
}
"""


def extract_product_snapshot(page: PageLike, url: str) -> ProductSnapshot:
    raw = page.evaluate(SNAPSHOT_SCRIPT)
    if not raw or not raw.get("packages"):
        raise SchemaDriftError("Nuxt option-section 缺少商品或套餐结构")
    match = re.search(r"/product/(\d+)", url)
    product_id = str(raw.get("productId") or (match.group(1) if match else ""))
    if not product_id:
        raise SchemaDriftError("Nuxt option-section 与 URL 都缺少商品 ID")
    packages = tuple(
        PackageRef(
            package_id=str(package["packageId"]),
            name=str(package.get("name") or ""),
            item_ids=tuple(str(item_id) for item_id in package.get("itemIds", [])),
            description=str(package.get("description") or ""),
        )
        for package in raw["packages"]
    )
    if any(not package.package_id or not package.item_ids for package in packages):
        raise SchemaDriftError("Nuxt 套餐缺少 package ID 或 item ID")
    return ProductSnapshot(
        product_id=product_id,
        url=url,
        name=str(raw.get("name") or ""),
        packages=packages,
    )


class ProductScraper:
    def __init__(
        self,
        page: PageLike,
        api: BrowserApiClient,
        *,
        sleep: Callable[[float], None] = sleep,
        uniform: Callable[[float, float], float] = uniform,
        continue_run: Callable[[], bool] = lambda: True,
        readiness_reporter: Callable[[ReadinessReport], None] = lambda _report: None,
    ) -> None:
        self.page = page
        self.api = api
        self.sleep = sleep
        self.uniform = uniform
        self.continue_run = continue_run
        self.readiness_reporter = readiness_reporter

    def _read_with_retry(
        self, operation: Callable[[], dict], config: RunConfig
    ) -> dict:
        attempts = len(config.request_retry_delays) + 1
        for attempt in range(attempts):
            try:
                return operation()
            except (SessionBlockedError, SessionExpiredError, ApiSchemaError):
                raise
            except BrowserApiError:
                if attempt == attempts - 1:
                    raise
                self.sleep(config.request_retry_delays[attempt])
        raise AssertionError("unreachable")

    def scrape(
        self, input_item: InputItem, probe: SessionProbe, config: RunConfig
    ) -> ProductResult:
        failures: list[FailureRecord] = []
        warnings: list[str] = []
        rows = []
        report = ReadinessReport(
            browser_connected=probe.connected,
            member_api_ready=probe.member_api_ready,
            product_page_ready=None,
            price_calendar_ready=None,
            sku_api_ready=None,
            product_url=input_item.url,
            currency=probe.currency,
            reason=probe.block_reason,
            is_login=probe.is_login,
        )

        def publish(**changes) -> None:
            nonlocal report
            report = replace(report, **changes)
            self.readiness_reporter(report)

        if not probe.member_api_ready:
            return ProductResult(
                input_item,
                None,
                (),
                (
                    FailureRecord(
                        FailureKind.SESSION_BLOCKED,
                        input_item.url,
                        "probe",
                        probe.block_reason or "会话不可用",
                        False,
                        input_item.input_order,
                    ),
                ),
            )

        if probe.currency.upper() != config.currency:
            message = (
                f"浏览器会话返回币种 {probe.currency or '未知'}，"
                f"与目标币种 {config.currency} 不一致"
            )
            publish(reason=message)
            return ProductResult(
                input_item,
                None,
                (),
                (
                    FailureRecord(
                        FailureKind.CURRENCY_MISMATCH,
                        input_item.url,
                        "currency",
                        message,
                        False,
                        input_item.input_order,
                    ),
                ),
            )

        response = None
        try:
            response = self.page.goto(
                input_item.url,
                wait_until="domcontentloaded",
                timeout=60_000,
            )
            self.page.wait_for_function(
                "() => Boolean(window.__NUXT__?.pinia?.['option-section']?.packages)",
                timeout=45_000,
            )
            snapshot = extract_product_snapshot(self.page, input_item.url)
            publish(product_page_ready=True, reason=None)
        except SchemaDriftError as exc:
            publish(product_page_ready=False, reason=f"商品页结构异常：{exc}")
            return ProductResult(
                input_item,
                None,
                (),
                (
                    FailureRecord(
                        FailureKind.SCHEMA,
                        input_item.url,
                        "snapshot",
                        str(exc),
                        False,
                        input_item.input_order,
                    ),
                ),
            )
        except Exception as exc:
            try:
                diagnostic = self.page.evaluate(PAGE_DIAGNOSTIC_SCRIPT) or {}
            except Exception:
                diagnostic = {}
            status = int(getattr(response, "status", 0) or 0)
            challenged = status in {401, 403} or bool(
                diagnostic.get("challenge")
            )
            if challenged:
                match = re.search(r"/product/(\d+)", input_item.url)
                calendar_ready = False
                if match:
                    try:
                        self.api.fetch_package_calendar(
                            match.group(1),
                            config.usage_date,
                            config.usage_date + timedelta(days=40),
                        )
                        calendar_ready = True
                    except (SessionBlockedError, SessionExpiredError):
                        publish(
                            product_page_ready=False,
                            price_calendar_ready=False,
                            sku_api_ready=False,
                            reason="商品页与 SKU 接口均被拦截",
                        )
                        raise
                    except Exception:
                        calendar_ready = False
                reason = (
                    "商品页被拦截，价格日历可用，但无法取得 SKU 树"
                    if calendar_ready
                    else "商品页被拦截，无法取得 SKU 树"
                )
                publish(
                    product_page_ready=False,
                    price_calendar_ready=calendar_ready,
                    sku_api_ready=None,
                    reason=reason,
                )
                raise SessionBlockedError(reason) from exc

            current_url = str(diagnostic.get("url") or self.page.url)
            if (
                diagnostic.get("readyState") == "complete"
                and "/product/" in current_url
            ):
                reason = "商品页结构异常：Nuxt option-section 缺少商品或套餐结构"
                publish(product_page_ready=False, reason=reason)
                return ProductResult(
                    input_item,
                    None,
                    (),
                    (
                        FailureRecord(
                            FailureKind.SCHEMA,
                            input_item.url,
                            "snapshot",
                            reason,
                            False,
                            input_item.input_order,
                        ),
                    ),
                )
            publish(product_page_ready=False, reason=f"商品导航失败：{exc}")
            return ProductResult(
                input_item,
                None,
                (),
                (
                    FailureRecord(
                        FailureKind.NAVIGATION,
                        input_item.url,
                        "snapshot",
                        str(exc),
                        True,
                        input_item.input_order,
                    ),
                ),
            )

        end_date = config.usage_date + timedelta(days=40)
        if not self.continue_run():
            return ProductResult(
                input_item,
                snapshot,
                (),
                warnings=("用户在价格日历请求前停止",),
            )
        try:
            calendar = self._read_with_retry(
                lambda: self.api.fetch_package_calendar(
                    snapshot.product_id, config.usage_date, end_date
                ),
                config,
            )
            publish(price_calendar_ready=True, reason=None)
        except (SessionBlockedError, SessionExpiredError):
            publish(
                price_calendar_ready=False,
                sku_api_ready=False,
                reason="价格日历接口被拦截",
            )
            raise
        except ApiSchemaError as exc:
            publish(price_calendar_ready=False, reason=f"价格日历结构异常：{exc}")
            return ProductResult(
                input_item,
                snapshot,
                (),
                (
                    FailureRecord(
                        FailureKind.SCHEMA,
                        input_item.url,
                        "package_calendar",
                        str(exc),
                        False,
                        input_item.input_order,
                    ),
                ),
            )
        except Exception as exc:
            publish(price_calendar_ready=False, reason=f"价格日历请求失败：{exc}")
            return ProductResult(
                input_item,
                snapshot,
                (),
                (
                    FailureRecord(
                        FailureKind.API,
                        input_item.url,
                        "package_calendar",
                        str(exc),
                        True,
                        input_item.input_order,
                    ),
                ),
            )

        for package_index, package in enumerate(snapshot.packages):
            if not self.continue_run():
                warnings.append("用户在套餐之间停止")
                break
            try:
                payload = self._read_with_retry(
                    lambda package=package: self.api.fetch_items_data(
                        package.package_id,
                        package.item_ids,
                        config.usage_date,
                        end_date,
                    ),
                    config,
                )
                if not self.continue_run():
                    warnings.append(f"用户在套餐 {package.package_id} 响应后停止")
                    break

                package_rows = []
                for item_id in package.item_ids:
                    package_rows.extend(
                        parse_item_payload(
                            payload=payload,
                            input_item=input_item,
                            product_id=snapshot.product_id,
                            product_name=snapshot.name,
                            package=package,
                            item_id=item_id,
                            usage_date=config.usage_date,
                            currency=probe.currency,
                        )
                    )
                if report.sku_api_ready is not True:
                    publish(sku_api_ready=True, reason=None)

                expected = package_minimum(
                    calendar, package.package_id, config.usage_date
                )
                valid, reason = validate_package_minimum(package_rows, expected)
                if not valid:
                    warnings.append(f"套餐 {package.package_id}: {reason}")
                    status = (
                        PriceStatus.MISSING
                        if "缺少价格" in reason
                        else PriceStatus.MINIMUM_MISMATCH
                    )
                    package_rows = [
                        replace(row, price_status=status, note=reason)
                        if row.available
                        else row
                        for row in package_rows
                    ]
                    failures.append(
                        FailureRecord(
                            FailureKind.MISSING_PRICE
                            if status is PriceStatus.MISSING
                            else FailureKind.PRICE_MISMATCH,
                            input_item.url,
                            f"package:{package.package_id}",
                            reason,
                            True,
                            input_item.input_order,
                        )
                    )
                rows.extend(package_rows)
            except (SessionBlockedError, SessionExpiredError):
                publish(sku_api_ready=False, reason="SKU 接口被拦截")
                raise
            except ApiSchemaError as exc:
                if report.sku_api_ready is not True:
                    publish(sku_api_ready=False, reason=f"SKU 接口结构异常：{exc}")
                failures.append(
                    FailureRecord(
                        FailureKind.SCHEMA,
                        input_item.url,
                        f"package:{package.package_id}",
                        str(exc),
                        False,
                        input_item.input_order,
                    )
                )
            except SchemaDriftError as exc:
                if report.sku_api_ready is not True:
                    publish(sku_api_ready=False, reason=f"SKU 数据结构异常：{exc}")
                failures.append(
                    FailureRecord(
                        FailureKind.SCHEMA,
                        input_item.url,
                        f"package:{package.package_id}",
                        str(exc),
                        False,
                        input_item.input_order,
                    )
                )
            except Exception as exc:
                if report.sku_api_ready is not True:
                    publish(sku_api_ready=False, reason=f"SKU 接口请求失败：{exc}")
                failures.append(
                    FailureRecord(
                        FailureKind.API,
                        input_item.url,
                        f"package:{package.package_id}",
                        str(exc),
                        True,
                        input_item.input_order,
                    )
                )

            if package_index + 1 < len(snapshot.packages):
                self.sleep(self.uniform(*config.package_delay_range))

        return ProductResult(
            input_item,
            snapshot,
            tuple(rows),
            tuple(failures),
            tuple(warnings),
        )
