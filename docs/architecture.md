# Architecture

## Truth hierarchy

1. Browser-context `fetch-items-data` response: SKU tree, sale price, item calendar, and close list.
2. Browser-context `fetch-packages-price-calendar` response: independent package minimum used for quality validation.
3. Nuxt Pinia `option-section`: product, package, item, and specification identifiers.
4. Visible DOM: manual diagnosis only; it is not the normal SKU enumeration path.

## Price rule

For the selected usage date and event `fullday`:

```text
available = calendar[date].is_saleable
            and not calendar[date].is_sold_out
            and event not in closeList[sku_oid][date]

sale_price = sku.single_price[event]
official_price = sku.official_price
```

`official_price` is never substituted for `sale_price`. A package is trusted only when all available SKUs have a sale price and their minimum equals the price-calendar minimum.

## Session rule

The program creates a tool-owned page inside the existing CDP browser context. This page inherits browser cookies and fingerprint, but Python never reads or persists those values. Direct HTTP is excluded from the production path because the verified endpoints returned `403` without browser credentials and still returned `403` when only browser-like header values were copied.

Chrome/Edge may expose only the browser WebSocket recorded in `DevToolsActivePort`, while returning `404` for `/json/version`. The session resolver reads that local transient path in memory, passes it directly to Playwright, and never logs or persists the WebSocket identifier. The member probe accepts the current member-status contract `result=BASE_SUCCESS` and exports only login boolean, currency, status, and block reason. It does not claim product or SKU readiness. The GUI keeps browser, member, product-page, package-calendar, and SKU-interface readiness separate; business readiness becomes true only after the first product supplies a Nuxt package tree, a valid calendar response, and a parsed `fetch-items-data` response.

There are two explicit browser entry points. 「连接现有浏览器」 is attach-only and never launches anything. 「一键启动调试浏览器」 starts or reuses a dedicated persistent Edge profile (Chrome fallback only when Edge is not installed), opens the KKday home page, and passes the in-memory `DevToolsActivePort` WebSocket directly to Playwright. It never calls `/json/version`, passes an HTTP address to Playwright, closes a default browser, or copies its profile data. The first run requires manual KKday login in the dedicated window; a later explicit reconnect re-probes the same session.

The dedicated profiles live outside the project at `~/Library/Application Support/KKdayScraper/browser-profiles/{edge,chrome}`. Bootstrap uses a profile-level lock. A valid running instance is reused; an unreachable transient `DevToolsActivePort` is removed only when Chromium no longer owns the profile lock, while an occupied profile fails closed instead of launching a duplicate. The GUI shows browser connection, member login, product page, price calendar, and SKU interface as separate readiness layers.

## Failure stop rules

- `401`, `403`, HTML response, or DataDome challenge: stop the batch and require an explicit browser probe.
- A blocked product page may still have a working package-calendar endpoint. This is diagnostic evidence only: without the Nuxt package/item tree, the batch fails closed and never claims SKU readiness.
- A normal completed product document without the expected Nuxt package tree is schema drift, not a member-session failure.
- Network/5xx/read timeout: retry twice with 1-second and 3-second waits, then record a retryable API failure.
- Missing Nuxt fields or non-empty unrecognized `skusPriceCalendar`: record non-trusted schema failure; do not click every SKU or invent a response shape.
- Available SKU without `single_price.fullday`: record missing price.
- SKU minimum different from package calendar: record minimum mismatch.
- User stop: finish the in-flight read, atomically save completed products, and exit the batch.

## Security boundary

Allowed durable data: product URL/ID, package/item/SKU IDs, specification names, availability, price, currency, endpoint path shape, status classification, and timestamps.

Forbidden durable data: Cookie values, Authorization values, CSRF values, passwords, OTP/verification codes, member UUIDs, login IDs, email, phone, passport data, and raw member-status responses.
