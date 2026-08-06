# Adversarial Review Remediation Implementation Plan

> **Execution:** Use Codex-native subagents and primary-agent integration. The repository AGENTS instructions explicitly prohibit the legacy executing-plans and subagent-driven-development skills.

**Goal:** Fix every confirmed adversarial-review finding with regression tests, one reviewable commit per problem boundary, and no authenticated browser or remote-state operation.

**Architecture:** Preserve the existing single-worker scraper architecture while making run outcomes explicit, separating dedicated-browser mutation from attach-only observation, validating all persisted/browser endpoints at trust boundaries, and making inputs and outputs collision-safe. Each task follows RED → GREEN → full targeted verification → commit.

**Tech Stack:** Python 3.11+, pytest, Playwright sync API, openpyxl, setuptools.

## Global Constraints

- Preserve the five commits already ahead of `origin/main`; do not rewrite history or push.
- Do not connect to a real browser, read real cookies, call KKday, or touch remote Hermes state.
- Every production behavior change requires a failing regression test first.
- Keep each commit limited to the named finding group; documentation follows the code boundary it describes.
- A successful run requires a completed terminal outcome, full input coverage, a successful final checkpoint, and a real output path.

---

### Task 1: Terminal outcome and CLI exit correctness

**Files:**
- Modify: `kkday_scraper/models.py`
- Modify: `kkday_scraper/task_runner.py`
- Modify: `kkday_scraper/cli.py`
- Test: `tests/test_task_runner.py`
- Test: `tests/test_cli.py`

**Produces:** A structured `RunResult` terminal outcome that records requested/processed counts, checkpoint success and run-level failure; every member-probe path reaches a final checkpoint and `FINISHED`; CLI exit zero is impossible for blocked, incomplete or unsaved runs.

- [ ] Add failing tests for a second-item blocked probe, a probe exception after partial progress, and checkpoint failure reaching CLI.
- [ ] Run the named tests and confirm the expected false-success/finalization failures.
- [ ] Add the minimal result/outcome fields and a single terminal finalization path.
- [ ] Run task-runner and CLI tests, then the full suite.
- [ ] Commit as `fix: make scraper terminal outcomes authoritative`.

### Task 2: Browser ownership and local CDP boundary

**Files:**
- Modify: `kkday_scraper/browser_session.py`
- Modify: `kkday_scraper/browser_bootstrap.py`
- Modify: `kkday_scraper/models.py` only if Task 1 has completed and an explicit endpoint ownership field is required
- Test: `tests/test_browser_session.py`
- Test: `tests/test_browser_bootstrap.py`
- Modify: `README.md`
- Modify: `docs/architecture.md`

**Produces:** Loopback-only CDP resolution; no direct arbitrary ws/wss input; preference injection only for a verified dedicated endpoint; attach-existing remains non-mutating and does not discover default daily profiles implicitly.

- [ ] Add failing tests for remote HTTP/WS rejection and attach-existing not calling `add_cookies()`.
- [ ] Run the named tests and confirm each missing boundary fails.
- [ ] Implement explicit dedicated versus attach behavior with loopback/path validation.
- [ ] Update the documented attach-only contract.
- [ ] Run browser tests and full suite.
- [ ] Commit as `fix: enforce dedicated browser ownership boundaries`.

### Task 3: Strict preference-cookie storage and credential-safe documentation

**Files:**
- Modify: `kkday_scraper/cookie_store.py`
- Create: `tests/test_cookie_store.py`
- Modify: `README.md`
- Modify: `HERMES.md`
- Modify: `hermes-agent/skills/kkday-sku-price-scraper-operations/SKILL.md`

**Produces:** Save and load share one strict whitelist validator; only the intended KKday host/path/security attributes are accepted; all full-cookie capture instructions are removed.

- [ ] Add failing tests for suffix-confusion domains, tampered loaded records, extra keys, file mode and corrupt input.
- [ ] Run the new tests and confirm the unsafe domains currently pass.
- [ ] Implement strict normalization on both save and load.
- [ ] Replace `Network.getAllCookies` instructions with explicit approved-value construction plus member-probe verification.
- [ ] Run cookie/session tests and search docs to prove full-cookie APIs are absent.
- [ ] Commit as `fix: harden preference cookie handling`.

### Task 4: Collision-safe run artifacts

**Files:**
- Modify: `kkday_scraper/exporter.py`
- Test: `tests/test_exporter.py`
- Modify: `README.md`
- Modify: `hermes-agent/skills/kkday-sku-price-scraper-operations/SKILL.md`

**Produces:** Unique default run directories, exclusive explicit-result-directory ownership, and one batch ID embedded consistently in the machine-readable summary and workbook summary.

- [ ] Add failing tests for same-instant exporter creation and explicit-directory contention.
- [ ] Run tests and confirm both exporters currently share a directory.
- [ ] Implement collision-resistant IDs and a recoverable lock/ownership marker.
- [ ] Add batch ID assertions across artifacts and document contention behavior.
- [ ] Run exporter tests and full suite.
- [ ] Commit as `fix: isolate concurrent scraper artifacts`.

### Task 5: Bounded and consistent inputs

**Files:**
- Modify: `kkday_scraper/inputs.py`
- Modify: `kkday_scraper/cli.py`
- Modify: `kkday_scraper/product_scraper.py`
- Test: `tests/test_inputs.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_product_scraper.py`

**Produces:** Streaming TXT/XLSX ingestion with byte/row/column/cell/URL limits, one numeric product-ID contract, and ASCII-only three-letter currencies.

- [ ] Add failing tests for Unicode currency, non-numeric product IDs, oversized TXT/cell/worksheet and URL-count limits.
- [ ] Run the named tests and record expected failures.
- [ ] Implement the smallest explicit limits and consistent product-ID parsing.
- [ ] Run input/parser tests and full suite.
- [ ] Commit as `fix: bound and normalize scraper inputs`.

### Task 6: GUI date and bounded shutdown semantics

**Files:**
- Modify: `kkday_scraper/gui.py`
- Modify: `kkday_scraper/task_runner.py`
- Modify: `kkday_scraper/browser_session.py` only after Task 2 is integrated
- Test: `tests/test_gui.py`
- Test: `tests/test_task_runner.py`
- Modify: `README.md`

**Produces:** GUI and CLI both default to the next calendar day; shutdown reports a bounded wait and can interrupt only the tool-owned page without closing an attached browser.

- [ ] Add failing tests for GUI next-day default and a controlled blocking browser operation during shutdown.
- [ ] Run the tests and confirm current same-day/unbounded behavior.
- [ ] Implement the date correction and bounded tool-page interruption contract.
- [ ] Run GUI/worker tests and full suite.
- [ ] Commit as `fix: bound shutdown and align default dates`.

### Task 7: Reproducible dependency and release gates

**Files:**
- Create: `requirements.lock`
- Modify: `pyproject.toml`
- Modify: `docs/hemis-agent-deployment.md`
- Modify: `README.md`
- Add CI configuration only if the repository already has a CI directory; otherwise document exact local gates without inventing a hosting workflow.

**Produces:** Pinned direct/transitive dependencies with hashes or an equivalent reproducible lock, project-isolated installation instructions, and documented `pip-audit`/test/compile gates.

- [ ] Inventory the currently resolved dependency tree and supported Python target.
- [ ] Generate a deterministic lock without upgrading production dependencies during this repair.
- [ ] Replace shared user-site installation instructions with an isolated environment and verified wheel workflow.
- [ ] Verify locked installation metadata, `pip check`, compile, tests and an available vulnerability audit; report if the audit tool is unavailable.
- [ ] Commit as `build: make scraper dependencies reproducible`.

### Task 8: Final adversarial regression and plan reconciliation

**Files:**
- Modify only files needed to correct regressions introduced by Tasks 1-7; fixes must be folded into the responsible commit when practical, otherwise use one explicit integration-fix commit.

- [ ] Re-read every finding and map it to code, test and commit.
- [ ] Run the complete non-live suite, compileall, `pip check`, doc secret-pattern gates and `git diff --check`.
- [ ] Inspect `git log`, `git status`, and every commit diff for scope separation.
- [ ] Confirm no authenticated/live/remote acceptance was performed and report that boundary.
