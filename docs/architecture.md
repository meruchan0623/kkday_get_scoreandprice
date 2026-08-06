# Architecture

The application has one browser runtime: ego-browser supplied by ego lite. Python invokes `ego-browser nodejs` through a project-local synchronous bridge. Each operation starts with `useOrCreateTaskSpace(nameOrId)`, and the returned numeric ID is reused for the rest of the batch.

`EgoBrowserBridge` exposes the minimum page contract consumed by the existing business layer: navigation, current URL, page JavaScript evaluation, and condition waiting. Authenticated KKday requests remain browser-context `fetch` calls with `credentials: include`; there is no direct Python HTTP fallback.

The data truth hierarchy is unchanged:

1. browser-context product and item API responses;
2. package calendar minimums and availability;
3. Nuxt/Pinia option-section state;
4. DOM diagnostics only, never an unverified price truth.

Python never reads login state material. The only browser state it may write is the validated preference-cookie whitelist: `currency`, `country_lang`, and `lang_ui`. Runtime errors are sanitized before becoming JSONL events.

Task-space ownership is fail-closed. `user is controlling`, inactive, or unassigned states stop the operation without retry, takeover, replacement space, or another browser runtime. A challenge preserves the task space and emits a structured Agent recovery prompt. CAPTCHA, MFA, account selection, and security confirmation require user handoff; takeover is allowed only after explicit confirmation.

Normal completion uses a dedicated final ego-browser invocation containing only `completeTaskSpace(id, {keep:false})`. Blocked runs do not complete the space, so the visible page remains available for recovery.

The GUI keeps all ego-browser bridge calls on one worker thread. The CLI and GUI share `TaskRunner`, price validation, checkpointing, and exporter behavior. Intermediate output is explicitly named `kkday_price_results.partial.xlsx`; final output is `kkday_price_results.xlsx`.
