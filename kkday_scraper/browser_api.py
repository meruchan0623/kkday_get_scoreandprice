from __future__ import annotations

import json
from datetime import date
from typing import Protocol
from urllib.parse import quote


class PageLike(Protocol):
    def evaluate(self, script: str, arg: dict) -> dict: ...


class BrowserApiError(RuntimeError):
    pass


class SessionBlockedError(BrowserApiError):
    pass


class SessionExpiredError(BrowserApiError):
    pass


class ApiSchemaError(BrowserApiError):
    pass


FETCH_SCRIPT = """
async ({ path, market, timeoutMs }) => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(path, {
      method: "GET",
      credentials: "include",
      headers: { market },
      signal: controller.signal
    });
    return {
      status: response.status,
      contentType: response.headers.get("content-type") || "",
      text: await response.text()
    };
  } finally {
    clearTimeout(timer);
  }
}
"""


# The frontend has already made this public request while loading the current
# product.  Reuse only its same-origin, allowlisted URL after checking that it
# names the product we are scraping.  In particular, do not reconstruct a
# query from guesses or copy credentials/headers into Python.
ORIGINAL_PACKAGES_DATA_SCRIPT = """
async ({ expectedProdMid, market, timeoutMs }) => {
  const endpoint = "/api/_nuxt/product/fetch-packages-data";
  const isPublicQuery = (url) => {
    for (const [key, value] of url.searchParams) {
      // Some public frontend URLs carry this empty flag.  A value would be a
      // credential-like token and is never replayed.
      if (key === "previewToken" && value === "") continue;
      if (/token|auth|cookie|session|signature|secret|key/i.test(key)) return false;
      if (key === "prodMid" && value === expectedProdMid) continue;
      if ((key === "beginDate" || key === "endDate") && /^\\d{4}-\\d{2}-\\d{2}$/.test(value)) continue;
      if (key === "platform" && /^[A-Z_]{1,32}$/.test(value)) continue;
      if (key === "extendedTimeout" && /^(true|false)$/.test(value)) continue;
      return false;
    }
    return true;
  };
  let path = null;
  for (const entry of performance.getEntriesByType("resource").slice().reverse()) {
    let url;
    try { url = new URL(entry.name); } catch (_) { continue; }
    if (url.origin !== location.origin || url.pathname !== endpoint) continue;
    if (url.searchParams.get("prodMid") !== expectedProdMid || !isPublicQuery(url)) continue;
    path = url.pathname + url.search;
    break;
  }
  if (!path) return { source: "not_found" };
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(path, {
      method: "GET", credentials: "include", headers: { market }, signal: controller.signal
    });
    return {
      source: "performance", status: response.status,
      contentType: response.headers.get("content-type") || "", text: await response.text()
    };
  } finally {
    clearTimeout(timer);
  }
}
"""


class BrowserApiClient:
    def __init__(self, page: PageLike, market: str, timeout_ms: int) -> None:
        self.page = page
        self.market = market
        self.timeout_ms = timeout_ms

    def set_market(self, market: str) -> None:
        """Change the market header used by subsequent browser-context fetches.

        Allows a single run to serve products from different KKday markets
        (e.g. zh-hk and zh-tw) by switching the request header per item.
        """
        self.market = market

    def get_json(self, path: str) -> dict:
        try:
            raw = self.page.evaluate(
                FETCH_SCRIPT,
                {
                    "path": path,
                    "market": self.market,
                    "timeoutMs": self.timeout_ms,
                },
            )
        except Exception as exc:
            raise BrowserApiError(
                f"浏览器内请求失败：{type(exc).__name__}: {exc}"
            ) from exc
        return self._decode_json_response(raw)

    def _decode_json_response(self, raw: object) -> dict:
        if not isinstance(raw, dict):
            raise ApiSchemaError("KKday API 返回了未知响应结构")

        status = int(raw.get("status") or 0)
        content_type = str(raw.get("contentType") or "").lower()
        if status == 401:
            raise SessionExpiredError("KKday 会话返回 401")
        if status == 403 or "text/html" in content_type:
            raise SessionBlockedError("KKday 返回 403/HTML challenge")
        if status != 200:
            raise BrowserApiError(f"KKday API 返回 HTTP {status}")
        try:
            payload = json.loads(str(raw.get("text") or ""))
        except json.JSONDecodeError as exc:
            raise ApiSchemaError("KKday API 未返回合法 JSON") from exc
        if (
            not isinstance(payload, dict)
            or payload.get("message") != "success"
            or "data" not in payload
        ):
            raise ApiSchemaError("KKday API 缺少 message=success/data 契约")
        return payload

    def fetch_package_calendar(
        self, product_id: str, begin_date: date, end_date: date
    ) -> dict:
        return self.get_json(
            "/api/_nuxt/product/fetch-packages-price-calendar"
            f"?beginDate={begin_date.isoformat()}"
            f"&endDate={end_date.isoformat()}"
            f"&prodOid={quote(product_id)}"
            "&previewToken"
        )

    def fetch_packages_data(
        self, product_id: str, begin_date: date, end_date: date
    ) -> dict:
        """Reuse the current page's verified public package graph request.

        Dates are deliberately not synthesized here: the loaded frontend URL
        is the contract.  No candidate means schema drift, rather than a
        request replay with an invented query shape.
        """
        del begin_date, end_date
        try:
            raw = self.page.evaluate(
                ORIGINAL_PACKAGES_DATA_SCRIPT,
                {
                    "expectedProdMid": str(product_id),
                    "market": self.market,
                    "timeoutMs": self.timeout_ms,
                },
            )
        except Exception as exc:
            raise BrowserApiError(
                f"浏览器内读取原始套餐资源失败：{type(exc).__name__}: {exc}"
            ) from exc
        if isinstance(raw, dict) and raw.get("source") == "not_found":
            raise ApiSchemaError("当前商品页未发现已验证的公开 fetch-packages-data 请求")
        return self._decode_json_response(raw)

    def fetch_items_data(
        self,
        package_id: str,
        item_ids: tuple[str, ...],
        begin_date: date,
        end_date: date,
    ) -> dict:
        if not item_ids:
            raise ValueError("fetch-items-data 至少需要一个 item ID")
        joined = quote(",".join(item_ids))
        repeated = "&".join(
            f"itemOidList%5B%5D={quote(item_id)}" for item_id in item_ids
        )
        return self.get_json(
            "/api/_nuxt/product/fetch-items-data"
            f"?pkgOid={quote(package_id)}"
            f"&itemOidList={joined}"
            f"&beginDate={begin_date.isoformat()}"
            f"&endDate={end_date.isoformat()}"
            "&vertical=DEFAULT"
            "&shouldInstantCalendar=false"
            "&previewToken"
            f"&{repeated}"
        )
