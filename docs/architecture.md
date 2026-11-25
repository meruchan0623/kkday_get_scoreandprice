# Architecture

The application has one browser runtime: ego-browser supplied by ego lite. Python invokes `ego-browser nodejs` through a project-local synchronous bridge. Each operation starts with `useOrCreateTaskSpace(nameOrId)`, and the returned numeric ID is reused for the rest of the batch.

`EgoBrowserBridge` exposes the minimum page contract consumed by the existing business layer: navigation, current URL, page JavaScript evaluation, and condition waiting. Authenticated KKday requests remain browser-context `fetch` calls with `credentials: include`; there is no direct Python HTTP fallback.

The data truth hierarchy is unchanged:

1. browser-context product and item API responses;
2. package calendar minimums and availability;
3. Nuxt/Pinia option-section state;
4. DOM diagnostics only, never an unverified price truth.

## SSR-less product-page graph

For product pages that omit Nuxt SSR entirely, `EgoPage` installs a
new-document passive observer before navigation. It retains only the normal
frontend `fetch-packages-data` graph in the page JavaScript heap after checking
the exact page origin/path, the request `prodMid`, numeric response
`PRODUCT-SETTING.prod_mid`, and every package/item key-to-OID association.
The product title is read from the actual `h1`. This graph is solely an
identity and SKU-tree source: it does not replace the item-price or calendar
requests, and it is not logged or written to disk as a raw response.

Limitations: it is intentionally unavailable if the page does not make that
normal request, its response changes the numeric ID contract, or the observed
graph is incomplete. In those cases the scraper remains fail-closed; it does
not infer IDs from labels, replay requests, or use a DOM price.

Python never reads login state material. The only browser state it may write is the validated preference-cookie whitelist: `currency`, `country_lang`, and `lang_ui`. Runtime errors are sanitized before becoming JSONL events.

Task-space ownership is fail-closed. `user is controlling`, inactive, or unassigned states stop the operation without retry, takeover, replacement space, or another browser runtime. A challenge preserves the task space and emits a structured Agent recovery prompt. CAPTCHA, MFA, account selection, and security confirmation require user handoff; takeover is allowed only after explicit confirmation.

Normal completion uses a dedicated final ego-browser invocation containing only `completeTaskSpace(id, {keep:false})`. Blocked runs do not complete the space, so the visible page remains available for recovery.

The GUI keeps all ego-browser bridge calls on one worker thread. The CLI and GUI share `TaskRunner`, price validation, checkpointing, and exporter behavior. Intermediate output is explicitly named `kkday_price_results.partial.xlsx`; final output is `kkday_price_results.xlsx`.
