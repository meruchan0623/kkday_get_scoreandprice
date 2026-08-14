from __future__ import annotations

import re
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
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
from .inputs import extract_product_id_from_url
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
  // KKday's newer Nuxt pages no longer hydrate option-section into window.__NUXT__.
  // Their SSR payload still has the verified resource graph:
  // PRODUCT.prodInfo.packages -> PACKAGE.<pkg_oid>.items -> ITEM.<item_oid>.
  // Decode only that graph; never infer package/item IDs from visible labels.
  if (!option || !option.packages) {
    const payloadText = Array.from(document.scripts)
      .map(node => node.textContent || "")
      .find(text => text.includes('"option-section"') && text.includes('"pkg_oid"'));
    if (!payloadText) return null;
    let encoded;
    try { encoded = JSON.parse(payloadText); } catch (_) { return null; }
    const memo = new Map();
    const resolve = (index) => {
      if (typeof index !== "number") return index;
      if (memo.has(index)) return memo.get(index);
      const value = encoded[index];
      if (!Array.isArray(value) && (!value || typeof value !== "object")) return value;
      if (Array.isArray(value) && ["Reactive", "ShallowReactive", "Ref", "EmptyRef"].includes(value[0])) {
        return resolve(value[1]);
      }
      const output = Array.isArray(value) ? [] : {};
      memo.set(index, output);
      for (const [key, child] of Object.entries(value)) output[key] = resolve(child);
      return output;
    };
    const root = resolve(0);
    const match = location.pathname.match(/\/product\/(\d+)/);
    const productId = String((match && match[1]) || "");
    const packageIds = new Set();
    const packageById = new Map();
    const visited = new Set();
    const walk = (value) => {
      if (!value || typeof value !== "object" || visited.has(value)) return;
      visited.add(value);
      if (value.prodInfo && String(value.prodInfo.prod_mid || "") === productId) {
        for (const id of value.prodInfo.packages || []) packageIds.add(String(id));
      }
      if (value.pkg_oid != null && Array.isArray(value.items)) {
        packageById.set(String(value.pkg_oid), value);
      }
      for (const child of Object.values(value)) walk(child);
    };
    walk(root);
    const packages = Array.from(packageIds)
      .map(id => packageById.get(id))
      .filter(Boolean)
      .map(pkg => ({
        packageId: String(pkg.pkg_oid),
        name: String(pkg.name || ""),
        itemIds: (pkg.items || []).map(item => String(item)),
        description: ""
      }));
    if (!productId || !packages.length) return null;
    const title = (document.querySelector("h1") && document.querySelector("h1").textContent.trim()) || document.title;
    return {
      productId, url: location.href, name: String(title || ""), destination: "",
      rating: null, reviewCount: null, soldCount: null, wishlistCount: null,
      pageMinPrice: null, confirmation: "", cancellationPolicy: "", features: [], packages
    };
  }
  const productStore = window.__NUXT__.pinia.product && window.__NUXT__.pinia.product.product;
  const product = (productStore && productStore.prodInfo) || option.product || option.prodInfo || {};
  const packageIds = Array.from(product.packages || option.product?.packages || []);
  const packageById = option.packages;
  const orderedPackages = packageIds.length
    ? packageIds.map(id => packageById[String(id)]).filter(Boolean)
    : Object.values(packageById);
  const match = location.pathname.match(/\/product\/(\d+)/);
  const productId = String((option.productSetting && option.productSetting.prod_mid) || (match && match[1]) || "");
  const title =
    (product && (product.name || product.title)) ||
    (document.querySelector("h1") && document.querySelector("h1").textContent.trim()) ||
    document.title.replace(/\s*-\s*KKday\s*$/, "");
  return {
    productId,
    url: location.href,
    name: String(title || ""),
    destination: String(product.destinations?.destinations?.[0]?.parent_name || ""),
    rating: product.statistics?.rec_avg_score ?? null,
    reviewCount: product.statistics?.rec_num ?? null,
    soldCount: product.statistics?.order_num ?? null,
    wishlistCount: product.statistics?.wishlist_num ?? null,
    pageMinPrice: product.sale_price?.min_price ?? null,
    confirmation: product.immediately_confirm ? "立即确认" : "",
    cancellationPolicy: String(
      product.description_module?.PMDL_REFUND_POLICY?.content?.properties?.policy_type?.desc || ""
    ),
    features: (() => {
      const container = document.createElement("div");
      container.innerHTML = String(product.feature || "");
      return Array.from(container.querySelectorAll("li"))
        .map(node => String(node.textContent || "").trim())
        .filter(Boolean);
    })(),
    packages: orderedPackages.map(pkg => ({
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
    hasNuxtPackages: Boolean(
      window.__NUXT__?.pinia?.["option-section"]?.packages ||
      Array.from(document.scripts).some(node => {
        const value = node.textContent || "";
        return value.includes('"option-section"') && value.includes('"pkg_oid"');
      })
    )
  };
}
"""


class NoPackagesError(ValueError):
    """The product exists, but exposes no currently scrapeable packages."""


def extract_product_snapshot(page: PageLike, url: str) -> ProductSnapshot:
    raw = page.evaluate(SNAPSHOT_SCRIPT)
    if not raw or "packages" not in raw:
        raise SchemaDriftError("Nuxt option-section 缺少商品或套餐结构")
    if not raw["packages"]:
        raise NoPackagesError("商品当前没有可抓取套餐")
    url_product_id = extract_product_id_from_url(url)
    page_product_id = str(raw.get("productId") or "")
    if page_product_id and re.fullmatch(r"\d+", page_product_id) is None:
        raise SchemaDriftError("Nuxt option-section 商品 ID 必须为数字")
    if page_product_id and url_product_id and page_product_id != url_product_id:
        raise SchemaDriftError("Nuxt option-section 商品 ID 与输入 URL 不一致")
    product_id = page_product_id or url_product_id
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
        destination=str(raw.get("destination") or ""),
        rating=(float(raw["rating"]) if raw.get("rating") is not None else None),
        review_count=(int(raw["reviewCount"]) if raw.get("reviewCount") is not None else None),
        sold_count=(int(raw["soldCount"]) if raw.get("soldCount") is not None else None),
        wishlist_count=(int(raw["wishlistCount"]) if raw.get("wishlistCount") is not None else None),
        page_min_price=(Decimal(str(raw["pageMinPrice"])) if raw.get("pageMinPrice") is not None else None),
        confirmation=str(raw.get("confirmation") or ""),
        cancellation_policy=str(raw.get("cancellationPolicy") or ""),
        features=tuple(str(value) for value in raw.get("features", []) if value),
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
                """() => Boolean(
                    window.__NUXT__?.pinia?.['option-section']?.packages ||
                    Array.from(document.scripts).some(node => {
                        const value = node.textContent || '';
                        return value.includes('option-section') && value.includes('pkg_oid');
                    })
                )""",
                timeout=45_000,
            )
            snapshot = extract_product_snapshot(self.page, input_item.url)
            publish(product_page_ready=True, reason=None)
        except NoPackagesError as exc:
            publish(product_page_ready=True, reason=str(exc))
            return ProductResult(
                input_item,
                None,
                (),
                (
                    FailureRecord(
                        FailureKind.NO_PACKAGES,
                        input_item.url,
                        "snapshot",
                        str(exc),
                        False,
                        input_item.input_order,
                    ),
                ),
            )
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
                product_id = extract_product_id_from_url(input_item.url)
                calendar_ready = False
                if product_id:
                    try:
                        self.api.fetch_package_calendar(
                            product_id,
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
                for item_index, item_id in enumerate(package.item_ids):
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
                            market=input_item.market or config.market,
                            package_order=package_index,
                            item_order=item_index,
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
