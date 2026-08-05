# KKday SKU Price Scraper Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Python KKday desktop scraper so a real Chrome/Edge session supplies the valid anti-bot context, browser-context API calls return the complete SKU tree and prices, and a new Tkinter GUI safely runs single-URL and batch jobs with auditable exports.

**Architecture:** Keep `kkday_get_scoreandprice.pyw` as the double-click entrypoint, but move all behavior into a focused `kkday_scraper` package. Attach to an already-authorized CDP browser first, call KKday's read-only Nuxt endpoints with same-origin `fetch` inside the page, normalize the response with pure Python, and treat DOM interaction as a manual diagnostic rather than the normal extraction engine.

**Tech Stack:** Python 3.11+, Tkinter/ttk, Playwright sync API over CDP, openpyxl, pytest, standard-library dataclasses/Decimal/threading/queue.

## Global Constraints

- Preserve Python as the implementation language and preserve `kkday_get_scoreandprice.pyw` as the user-facing launcher.
- Support Python 3.11 or newer; the verified development machine currently uses Python 3.13.2, Tk 8.6, Playwright 1.55.0, openpyxl 3.1.5, and pytest 9.0.2.
- Prefer `connect_over_cdp("http://127.0.0.1:9222")`; only launch a dedicated persistent, visible browser when no reusable CDP browser exists.
- Never persist or log Cookie values, Authorization values, CSRF values, passwords, verification codes, or raw member records in Python/project artifacts. A dedicated fallback browser may keep its own normal browser profile under `~/.kkday_scraper/browser_profile`.
- Do not inject fake `window.chrome`, plugin arrays, languages, hardware concurrency, or device-memory values. The real browser profile is the anti-bot boundary.
- All KKday product HTTP calls must execute as same-origin browser `fetch` with `credentials: "include"`; direct `requests`, `httpx`, or `curl` is not a production fallback because the verified endpoints return 403 outside the browser session.
- The default run uses one browser worker and one active product at a time.
- Every selected price date is explicit. The GUI defaults to the local current date and never silently shifts a product to a different date.
- `single_price[event]` is the verified sale-price field. `official_price` is exported separately and must never substitute for a missing sale price.
- Availability requires both a saleable item calendar entry and absence from `closeList[sku_oid][date]` for the selected event.
- A product is `trusted` only when every available SKU has a sale price and the minimum available SKU price equals the package price-calendar minimum for the selected date.
- A non-empty, unrecognized `skusPriceCalendar` is schema drift: fail closed, record evidence without secrets, and do not guess a price.
- API retries are finite: at most two retries per read request, with 1-second then 3-second delays. A 401/403, HTML challenge response, or DataDome page stops the batch and requires an explicit user session probe before resume.
- Pause and stop are cooperative and checked before navigation, before each package request, after each response, and before export.
- Partial trusted results must remain exportable after stop or a later product failure.
- Default output is a timestamped run directory under `~/Downloads/KKday_scraping/` containing XLSX, `run_summary.json`, and `failures.jsonl` when failures exist.
- Default tests are offline and fixture-based. Live KKday tests are opt-in through environment variables and reuse an already-authorized CDP browser.
- Repository instructions override the legacy execution-skill recommendation in the header: execution must use Codex-native orchestration and must not invoke `superpowers:subagent-driven-development` or `superpowers:executing-plans`.

---

## First-Principles Runtime Contract

The rebuild follows five invariants:

1. **Browser session is transport, not data storage.** The browser contributes DataDome clearance, cookies, TLS/browser fingerprint, language, currency, and login state. Python only receives safe probe fields and business responses.
2. **Interfaces are the price truth.** `fetch-packages-price-calendar` supplies the independent package minimum; `fetch-items-data` supplies `item.skus`, `calendar`, `closeList`, and prices. The UI is not traversed for every SKU.
3. **Availability is date-specific.** A SKU tree without an explicit usage date is incomplete and must not be exported as current availability.
4. **Quality failures are data, not exceptions to hide.** Missing SKU prices, price-calendar mismatch, blocked sessions, and schema changes are exported as classified failures.
5. **The GUI orchestrates; it never scrapes.** Tk widgets send commands to a single worker and render typed events. Browser and parsing code remain testable without a display.

The expected run is:

```text
Launch GUI
  -> attach existing Chrome/Edge CDP session
  -> open/reuse a KKday page owned by the tool
  -> probe member/session status and currency
  -> load manual/TXT/Excel inputs
  -> for each product, navigate once
  -> read product/package/item identifiers from Nuxt Pinia state
  -> fetch package price calendar inside the page
  -> fetch item data once per package
  -> expand SKU specs, date availability, sale price, and original price
  -> cross-check every package minimum
  -> append trusted rows or a classified failure
  -> atomically refresh the partial workbook
  -> finalize workbook and run summary
```

The Trip.com program is used as a boundary reference, not copied mechanically. This plan borrows its typed input/result contracts, vendor-column Excel provenance, reporter events, partial export, and quality gates. It deliberately does not borrow multi-worker vendor scheduling, headless defaults, browser-restart loops, or comparison workbooks because KKday's verified DataDome path is a single real-browser session.

## Target File Structure

### Create

- `pyproject.toml` — Python version, runtime dependencies, pytest configuration, and package metadata.
- `kkday_scraper/__init__.py` — package version and public entrypoints.
- `kkday_scraper/models.py` — immutable input, session, package, SKU, product, run, failure, and UI-event models.
- `kkday_scraper/inputs.py` — manual URL, TXT, and vendor-column Excel input parsing with stable deduplication.
- `kkday_scraper/browser_session.py` — CDP attach-first browser ownership, dedicated-profile fallback, safe session probe, and detach/close behavior.
- `kkday_scraper/browser_api.py` — same-origin browser `fetch`, endpoint builders, timeout handling, and response classification.
- `kkday_scraper/sku_parser.py` — pure parsing of item payloads, spec-name resolution, availability, prices, and minimum-price quality checks.
- `kkday_scraper/product_scraper.py` — page navigation, Nuxt product snapshot, package iteration, finite retry, and per-product result assembly.
- `kkday_scraper/task_runner.py` — one-worker batch state machine, pause/stop, progress events, blocked-session stop rules, and partial results.
- `kkday_scraper/exporter.py` — atomic XLSX, summary JSON, and failure JSONL export.
- `kkday_scraper/gui_state.py` — pure button/status policy derived from the application phase.
- `kkday_scraper/gui.py` — ttk layout, input queue, date/output controls, worker bridge, log/result preview, and dialogs.
- `tests/fixtures/product_snapshot_149025.json` — sanitized package/item/spec identifiers from the verified product.
- `tests/fixtures/package_calendar_149025.json` — sanitized package calendar fixture.
- `tests/fixtures/items_data_476215.json` — sanitized daily/unlimited package fixture.
- `tests/fixtures/items_data_1982144.json` — sanitized total-data package fixture.
- `tests/test_models.py`
- `tests/test_inputs.py`
- `tests/test_browser_session.py`
- `tests/test_browser_api.py`
- `tests/test_sku_parser.py`
- `tests/test_product_scraper.py`
- `tests/test_task_runner.py`
- `tests/test_exporter.py`
- `tests/test_gui_state.py`
- `tests/test_live_kkday_contract.py`
- `README.md`
- `docs/architecture.md`

### Modify

- `kkday_get_scoreandprice.pyw` — replace the 1,600-line application with a compatibility launcher that imports `kkday_scraper.gui.main`.

### Remove after replacement tests pass

The legacy Selenium/undetected-chromedriver implementation disappears when `kkday_get_scoreandprice.pyw` becomes the launcher. No compatibility module keeps these obsolete behaviors reachable:

- `KKdayAntiDetectionHelper`
- Selenium driver creation and tab-switching code
- injected stealth scripts
- DOM DFS SKU enumeration
- fixed 20–300 ms wait loops
- price text scanning across arbitrary page elements
- undefined `retry` / `max_retries` price retry branch

---

### Task 1: Establish Package, Dependencies, and Domain Contracts

**Files:**
- Create: `pyproject.toml`
- Create: `kkday_scraper/__init__.py`
- Create: `kkday_scraper/models.py`
- Create: `tests/test_models.py`

**Interfaces:**
- Produces: `InputItem`, `RunConfig`, `SessionProbe`, `PackageRef`, `ProductSnapshot`, `SkuRow`, `FailureRecord`, `ProductResult`, `RunResult`, `RunPhase`, `EventKind`, and `AppEvent`.
- Produces: `RunConfig.usage_date: date`, `RunConfig.output_dir: Path`, `RunConfig.market: str`, and exact finite retry settings used by later tasks.
- Consumes: no earlier task.

- [ ] **Step 1: Write failing model tests**

Create `tests/test_models.py`:

```python
from datetime import date
from decimal import Decimal
from pathlib import Path

from kkday_scraper.models import (
    InputItem,
    PriceStatus,
    RunConfig,
    SkuRow,
)


def test_run_config_has_safe_finite_defaults(tmp_path: Path) -> None:
    config = RunConfig(usage_date=date(2026, 7, 22), output_dir=tmp_path)

    assert config.market == "zh-tw"
    assert config.cdp_url == "http://127.0.0.1:9222"
    assert config.request_timeout_ms == 30_000
    assert config.request_retry_delays == (1.0, 3.0)
    assert config.product_delay_range == (2.0, 4.0)
    assert config.package_delay_range == (0.4, 0.9)


def test_sku_row_keeps_sale_and_official_price_separate() -> None:
    row = SkuRow(
        vendor="手动输入",
        input_order=0,
        product_id="149025",
        product_url="https://www.kkday.com/zh-tw/product/149025-example",
        product_name="日本 eSIM",
        package_id="1982144",
        package_name="总量 eSIM",
        item_id="1727921",
        sku_id="6a7d217fd4e41d222a768a73de2a2ab7",
        usage_date=date(2026, 7, 22),
        options=("總量10GB", "3 日"),
        available=True,
        currency="KRW",
        sale_price=Decimal("10741"),
        official_price=Decimal("21483"),
        price_source="single_price.fullday",
        price_status=PriceStatus.TRUSTED,
    )

    assert row.sale_price == Decimal("10741")
    assert row.official_price == Decimal("21483")
    assert row.option_text == "總量10GB | 3 日"


def test_input_item_retains_excel_origin() -> None:
    item = InputItem(
        url="https://www.kkday.com/zh-tw/product/149025-example",
        vendor="TSIM 網址",
        input_order=2,
        source_path=Path("vendors.xlsx"),
        source_row=4,
        source_column=1,
    )

    assert item.source_row == 4
    assert item.source_column == 1
```

- [ ] **Step 2: Run the tests and verify the expected failure**

Run:

```bash
python3 -m pytest tests/test_models.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'kkday_scraper'`.

- [ ] **Step 3: Add project metadata and the complete domain model**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[project]
name = "kkday-sku-price-scraper"
version = "2.0.0"
requires-python = ">=3.11"
dependencies = [
  "openpyxl>=3.1,<4",
  "playwright>=1.50,<2",
]

[project.optional-dependencies]
dev = ["pytest>=8,<10"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["live: requires an authorized local KKday browser session"]
```

Create `kkday_scraper/__init__.py`:

```python
"""KKday SKU price scraper."""

__version__ = "2.0.0"
```

Create `kkday_scraper/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any


class RunPhase(str, Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


class PriceStatus(str, Enum):
    TRUSTED = "trusted"
    UNAVAILABLE = "unavailable"
    MISSING = "missing_price"
    MINIMUM_MISMATCH = "minimum_mismatch"
    SCHEMA_UNKNOWN = "schema_unknown"


class FailureKind(str, Enum):
    INPUT = "input"
    SESSION_BLOCKED = "session_blocked"
    SESSION_EXPIRED = "session_expired"
    NAVIGATION = "navigation"
    API = "api"
    SCHEMA = "schema"
    MISSING_PRICE = "missing_price"
    PRICE_MISMATCH = "price_mismatch"
    STOPPED = "stopped"


class EventKind(str, Enum):
    PHASE = "phase"
    LOG = "log"
    PROGRESS = "progress"
    PRODUCT_RESULT = "product_result"
    FAILURE = "failure"
    FINISHED = "finished"


@dataclass(frozen=True)
class InputItem:
    url: str
    vendor: str = "手动输入"
    input_order: int = 0
    source_path: Path | None = None
    source_row: int | None = None
    source_column: int | None = None


@dataclass(frozen=True)
class RunConfig:
    usage_date: date
    output_dir: Path
    market: str = "zh-tw"
    cdp_url: str = "http://127.0.0.1:9222"
    request_timeout_ms: int = 30_000
    request_retry_delays: tuple[float, ...] = (1.0, 3.0)
    product_delay_range: tuple[float, float] = (2.0, 4.0)
    package_delay_range: tuple[float, float] = (0.4, 0.9)
    include_unavailable: bool = False


@dataclass(frozen=True)
class SessionProbe:
    connected: bool
    api_ready: bool
    is_login: bool
    currency: str
    market: str
    page_url: str
    block_reason: str | None = None


@dataclass(frozen=True)
class PackageRef:
    package_id: str
    name: str
    item_ids: tuple[str, ...]
    description: str = ""


@dataclass(frozen=True)
class ProductSnapshot:
    product_id: str
    url: str
    name: str
    packages: tuple[PackageRef, ...]


@dataclass(frozen=True)
class SkuRow:
    vendor: str
    input_order: int
    product_id: str
    product_url: str
    product_name: str
    package_id: str
    package_name: str
    item_id: str
    sku_id: str
    usage_date: date
    options: tuple[str, ...]
    available: bool
    currency: str
    sale_price: Decimal | None
    official_price: Decimal | None
    price_source: str
    price_status: PriceStatus
    note: str = ""
    captured_at: datetime = field(default_factory=datetime.now)

    @property
    def option_text(self) -> str:
        return " | ".join(self.options)


@dataclass(frozen=True)
class FailureRecord:
    kind: FailureKind
    url: str
    stage: str
    message: str
    retryable: bool
    input_order: int | None = None
    captured_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class ProductResult:
    input_item: InputItem
    snapshot: ProductSnapshot | None
    rows: tuple[SkuRow, ...]
    failures: tuple[FailureRecord, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def trusted_rows(self) -> tuple[SkuRow, ...]:
        return tuple(row for row in self.rows if row.price_status is PriceStatus.TRUSTED)


@dataclass(frozen=True)
class RunResult:
    products: tuple[ProductResult, ...]
    output_path: Path | None
    started_at: datetime
    finished_at: datetime
    stopped: bool = False

    @property
    def rows(self) -> tuple[SkuRow, ...]:
        return tuple(row for product in self.products for row in product.rows)

    @property
    def failures(self) -> tuple[FailureRecord, ...]:
        return tuple(failure for product in self.products for failure in product.failures)


@dataclass(frozen=True)
class AppEvent:
    kind: EventKind
    message: str = ""
    phase: RunPhase | None = None
    current: int | None = None
    total: int | None = None
    payload: Any = None
```

- [ ] **Step 4: Run the model tests**

Run:

```bash
python3 -m pytest tests/test_models.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit the domain boundary**

```bash
git add pyproject.toml kkday_scraper/__init__.py kkday_scraper/models.py tests/test_models.py
git commit -m "refactor: establish KKday scraper domain contracts"
```

---

### Task 2: Add Manual, TXT, and Vendor-Excel Inputs

**Files:**
- Create: `kkday_scraper/inputs.py`
- Create: `tests/test_inputs.py`

**Interfaces:**
- Consumes: `InputItem` from Task 1.
- Produces: `normalize_product_url(raw: str) -> str`.
- Produces: `load_manual_urls(raw: str, start_order: int = 0) -> list[InputItem]`.
- Produces: `load_txt(path: Path, start_order: int = 0) -> list[InputItem]`.
- Produces: `load_vendor_excel(path: Path, start_order: int = 0) -> tuple[list[InputItem], list[str]]`.
- Produces: `deduplicate_inputs(items: list[InputItem]) -> list[InputItem]`.

- [ ] **Step 1: Write failing input tests**

Create `tests/test_inputs.py`:

```python
from pathlib import Path

import openpyxl
import pytest

from kkday_scraper.inputs import (
    deduplicate_inputs,
    load_manual_urls,
    load_txt,
    load_vendor_excel,
    normalize_product_url,
)


URL_A = "https://www.kkday.com/zh-tw/product/149025-example"
URL_B = "https://www.kkday.com/zh-tw/product/1982144-example"


def test_normalize_product_url_rejects_non_product_url() -> None:
    with pytest.raises(ValueError, match="KKday 商品 URL"):
        normalize_product_url("https://www.kkday.com/zh-tw/portable-travel-wifi-sim-card")


def test_manual_and_txt_inputs_preserve_order(tmp_path: Path) -> None:
    text_path = tmp_path / "urls.txt"
    text_path.write_text(f"{URL_B}\n\n", encoding="utf-8")

    items = load_manual_urls(f"{URL_A}\n{URL_A}") + load_txt(text_path, start_order=2)
    unique = deduplicate_inputs(items)

    assert [item.url for item in unique] == [URL_A, URL_B]
    assert [item.input_order for item in unique] == [0, 2]


def test_vendor_excel_reads_headers_and_source_coordinates(tmp_path: Path) -> None:
    path = tmp_path / "vendors.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["TSIM 網址", "BC"])
    sheet.append([URL_A, URL_B])
    sheet.append(["", "not-a-url"])
    workbook.save(path)

    items, warnings = load_vendor_excel(path)

    assert [(item.vendor, item.source_row, item.source_column) for item in items] == [
        ("TSIM 網址", 2, 1),
        ("BC", 2, 2),
    ]
    assert warnings == ["忽略非 KKday 商品 URL：工作表第 3 行，第 2 列：not-a-url"]
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
python3 -m pytest tests/test_inputs.py -q
```

Expected: collection fails because `kkday_scraper.inputs` does not exist.

- [ ] **Step 3: Implement exact input rules**

Create `kkday_scraper/inputs.py`:

```python
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import openpyxl

from .models import InputItem


PRODUCT_PATH_RE = re.compile(r"^/[a-z]{2}-[a-z]{2}/product/([A-Za-z0-9_-]+)(?:-|$|/)", re.IGNORECASE)


def normalize_product_url(raw: str) -> str:
    value = raw.strip()
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or parts.hostname not in {"kkday.com", "www.kkday.com"}:
        raise ValueError(f"不是有效的 KKday 商品 URL：{raw}")
    if PRODUCT_PATH_RE.search(parts.path) is None:
        raise ValueError(f"不是有效的 KKday 商品 URL：{raw}")
    return urlunsplit(("https", "www.kkday.com", parts.path, parts.query, ""))


def load_manual_urls(raw: str, start_order: int = 0) -> list[InputItem]:
    items: list[InputItem] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        items.append(InputItem(url=normalize_product_url(line), input_order=start_order + len(items)))
    return items


def load_txt(path: Path, start_order: int = 0) -> list[InputItem]:
    items: list[InputItem] = []
    for row_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        items.append(
            InputItem(
                url=normalize_product_url(line),
                input_order=start_order + len(items),
                source_path=path,
                source_row=row_number,
            )
        )
    return items


def load_vendor_excel(path: Path, start_order: int = 0) -> tuple[list[InputItem], list[str]]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    workbook.close()
    if not rows:
        raise ValueError("Excel 没有可读取的工作表内容")

    headers = [str(value).strip() if value is not None else "" for value in rows[0]]
    items: list[InputItem] = []
    warnings: list[str] = []
    for row_index, row in enumerate(rows[1:], start=2):
        for column_index, value in enumerate(row, start=1):
            text = str(value).strip() if value is not None else ""
            if not text:
                continue
            vendor = headers[column_index - 1] if column_index <= len(headers) else ""
            if not vendor:
                warnings.append(f"忽略无厂商表头的链接：工作表第 {row_index} 行，第 {column_index} 列")
                continue
            try:
                url = normalize_product_url(text)
            except ValueError:
                warnings.append(f"忽略非 KKday 商品 URL：工作表第 {row_index} 行，第 {column_index} 列：{text}")
                continue
            items.append(
                InputItem(
                    url=url,
                    vendor=vendor,
                    input_order=start_order + len(items),
                    source_path=path,
                    source_row=row_index,
                    source_column=column_index,
                )
            )
    return items, warnings


def deduplicate_inputs(items: list[InputItem]) -> list[InputItem]:
    seen: set[tuple[str, str]] = set()
    result: list[InputItem] = []
    for item in sorted(items, key=lambda candidate: candidate.input_order):
        key = (item.vendor, item.url)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
```

- [ ] **Step 4: Run the input tests**

Run:

```bash
python3 -m pytest tests/test_inputs.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit input support**

```bash
git add kkday_scraper/inputs.py tests/test_inputs.py
git commit -m "feat: add KKday URL and Excel batch inputs"
```

---

### Task 3: Build the Pure SKU Tree and Price Parser

**Files:**
- Create: `tests/fixtures/package_calendar_149025.json`
- Create: `tests/fixtures/items_data_476215.json`
- Create: `tests/fixtures/items_data_1982144.json`
- Create: `kkday_scraper/sku_parser.py`
- Create: `tests/test_sku_parser.py`

**Interfaces:**
- Consumes: `InputItem`, `PackageRef`, `PriceStatus`, and `SkuRow` from Task 1.
- Produces: `SchemaDriftError`.
- Produces: `parse_item_payload(...) -> list[SkuRow]`.
- Produces: `validate_package_minimum(rows: list[SkuRow], expected_minimum: Decimal | None) -> tuple[bool, str]`.
- Produces: `package_minimum(calendar_payload: dict, package_id: str, usage_date: date) -> Decimal | None`.

- [ ] **Step 1: Add minimal sanitized interface fixtures**

Create `tests/fixtures/package_calendar_149025.json`:

```json
{
  "status": 200,
  "message": "success",
  "data": {
    "packages": {
      "476215": {
        "pkg_oid": 476215,
        "calendar": {
          "2026-07-22": {"date": "2026-07-22", "min_price": 711, "base_min_price": 711}
        }
      },
      "1982144": {
        "pkg_oid": 1982144,
        "calendar": {
          "2026-07-22": {"date": "2026-07-22", "min_price": 10741, "base_min_price": 10741}
        }
      }
    }
  }
}
```

Create `tests/fixtures/items_data_476215.json`:

```json
{
  "status": 200,
  "message": "success",
  "data": {
    "221992": {
      "item": {
        "item_oid": 221992,
        "specs": [
          {
            "spec_oid": "traffic",
            "spec_title": "流量",
            "spec_items": [
              {"spec_item_oid": "unlimited", "name": "無限流量（保證不降速）"},
              {"spec_item_oid": "500mb", "name": "500MB/日"}
            ]
          },
          {
            "spec_oid": "spec-days",
            "spec_title": "天數",
            "spec_items": [
              {"spec_item_oid": "one-day", "name": "1 日"}
            ]
          }
        ],
        "skus": [
          {
            "sku_oid": "available-sku",
            "spec": {"traffic": "500mb", "spec-days": "one-day"},
            "official_price": null,
            "single_price": {"fullday": 711}
          },
          {
            "sku_oid": "closed-sku",
            "spec": {"traffic": "unlimited", "spec-days": "one-day"},
            "official_price": 15942,
            "single_price": {"fullday": 7971}
          }
        ]
      },
      "calendar": {
        "2026-07-22": {
          "date": "2026-07-22",
          "events": ["fullday"],
          "is_saleable": true,
          "is_sold_out": false
        }
      },
      "closeList": {
        "closed-sku": {"2026-07-22": ["fullday"]}
      },
      "skusPriceCalendar": null
    }
  }
}
```

Create `tests/fixtures/items_data_1982144.json`:

```json
{
  "status": 200,
  "message": "success",
  "data": {
    "1727921": {
      "item": {
        "item_oid": 1727921,
        "specs": [
          {
            "spec_oid": "traffic",
            "spec_title": "流量",
            "spec_items": [{"spec_item_oid": "10gb", "name": "總量10GB"}]
          },
          {
            "spec_oid": "spec-days",
            "spec_title": "天數",
            "spec_items": [{"spec_item_oid": "three-days", "name": "3 日"}]
          }
        ],
        "skus": [
          {
            "sku_oid": "discounted-sku",
            "spec": {"traffic": "10gb", "spec-days": "three-days"},
            "official_price": 21483,
            "single_price": {"fullday": 10741}
          }
        ]
      },
      "calendar": {
        "2026-07-22": {
          "date": "2026-07-22",
          "events": ["fullday"],
          "is_saleable": true,
          "is_sold_out": false
        }
      },
      "closeList": {},
      "skusPriceCalendar": null
    }
  }
}
```

- [ ] **Step 2: Write failing parser tests**

Create `tests/test_sku_parser.py`:

```python
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
```

- [ ] **Step 3: Run the tests and verify they fail**

Run:

```bash
python3 -m pytest tests/test_sku_parser.py -q
```

Expected: collection fails because `kkday_scraper.sku_parser` does not exist.

- [ ] **Step 4: Implement the verified SKU-price contract**

Create `kkday_scraper/sku_parser.py`:

```python
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from .models import InputItem, PackageRef, PriceStatus, SkuRow


class SchemaDriftError(ValueError):
    pass


def as_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def package_minimum(calendar_payload: dict, package_id: str, usage_date: date) -> Decimal | None:
    value = (
        calendar_payload.get("data", {})
        .get("packages", {})
        .get(str(package_id), {})
        .get("calendar", {})
        .get(usage_date.isoformat(), {})
        .get("min_price")
    )
    return as_decimal(value)


def _spec_name_maps(item: dict) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    titles: dict[str, str] = {}
    values: dict[str, dict[str, str]] = {}
    for spec in item.get("specs", []):
        spec_id = str(spec.get("spec_oid", ""))
        if not spec_id:
            raise SchemaDriftError("specs 中缺少 spec_oid")
        titles[spec_id] = str(spec.get("spec_title", spec_id))
        values[spec_id] = {
            str(option.get("spec_item_oid", "")): str(option.get("name", ""))
            for option in spec.get("spec_items", [])
            if option.get("spec_item_oid") is not None
        }
    return titles, values


def parse_item_payload(
    *,
    payload: dict,
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
        raise SchemaDriftError(f"fetch-items-data 缺少 item {item_id} 的必要字段") from exc

    dynamic = item_data.get("skusPriceCalendar")
    if dynamic not in (None, {}):
        raise SchemaDriftError("发现未验证的非空 skusPriceCalendar，拒绝猜测动态价格")

    _, option_maps = _spec_name_maps(item)
    close_list = item_data.get("closeList") or {}
    day_saleable = bool(calendar_day and calendar_day.get("is_saleable") and not calendar_day.get("is_sold_out"))
    rows: list[SkuRow] = []
    for sku in item.get("skus", []):
        sku_id = str(sku.get("sku_oid", ""))
        if not sku_id:
            raise SchemaDriftError(f"item {item_id} 的 SKU 缺少 sku_oid")
        spec_selection = sku.get("spec") or {}
        options: list[str] = []
        for spec_id, option_id in spec_selection.items():
            option_name = option_maps.get(str(spec_id), {}).get(str(option_id))
            if not option_name:
                raise SchemaDriftError(f"SKU {sku_id} 无法解析规格 {spec_id}={option_id}")
            options.append(option_name)

        closed_events = (
            close_list.get(sku_id, {})
            .get(usage_date.isoformat(), [])
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


def validate_package_minimum(rows: list[SkuRow], expected_minimum: Decimal | None) -> tuple[bool, str]:
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
```

- [ ] **Step 5: Run parser tests**

Run:

```bash
python3 -m pytest tests/test_sku_parser.py -q
```

Expected: `4 passed`.

- [ ] **Step 6: Commit the price truth layer**

```bash
git add kkday_scraper/sku_parser.py tests/fixtures tests/test_sku_parser.py
git commit -m "feat: parse KKday SKU availability and prices"
```

---

### Task 4: Attach to the Real Browser and Probe the Session Safely

**Files:**
- Create: `kkday_scraper/browser_session.py`
- Create: `tests/test_browser_session.py`

**Interfaces:**
- Consumes: `RunConfig` and `SessionProbe` from Task 1.
- Produces: `BrowserSession.connect() -> None`.
- Produces: `BrowserSession.page` for Tasks 5–7.
- Produces: `BrowserSession.probe(market: str) -> SessionProbe`.
- Produces: `BrowserSession.close() -> None`, which closes only the tool-owned page for attached browsers and closes the full context only for a tool-launched profile.
- Produces: `SessionUnavailableError` and `classify_probe(raw: dict, page_url: str, market: str) -> SessionProbe`.

- [ ] **Step 1: Write failing session-classification and ownership tests**

Create `tests/test_browser_session.py`:

```python
from pathlib import Path

from kkday_scraper.browser_session import BrowserSession, classify_probe
from kkday_scraper.models import RunConfig


class FakePage:
    def __init__(self, probe: dict) -> None:
        self.probe = probe
        self.closed = False
        self.url = "https://www.kkday.com/zh-tw"

    def evaluate(self, _script: str, _args: dict) -> dict:
        return self.probe

    def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class FakePlaywright:
    def __init__(self) -> None:
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1


def test_success_probe_exposes_only_safe_state() -> None:
    probe = classify_probe(
        {
            "status": 200,
            "contentType": "application/json",
            "isLogin": True,
            "currency": "KRW",
        },
        "https://www.kkday.com/zh-tw/product/149025-example",
        "zh-tw",
    )

    assert probe.connected is True
    assert probe.api_ready is True
    assert probe.is_login is True
    assert probe.currency == "KRW"
    assert not hasattr(probe, "cookie")


def test_html_403_probe_is_blocked() -> None:
    probe = classify_probe(
        {"status": 403, "contentType": "text/html;charset=utf-8", "isLogin": False, "currency": ""},
        "https://www.kkday.com/zh-tw",
        "zh-tw",
    )

    assert probe.api_ready is False
    assert probe.block_reason == "KKday 返回 403/HTML，浏览器会话需要人工验证"


def test_attached_session_close_never_closes_user_browser(tmp_path: Path) -> None:
    page = FakePage({})
    browser = FakeBrowser()
    playwright = FakePlaywright()
    session = BrowserSession(RunConfig(usage_date=__import__("datetime").date(2026, 7, 22), output_dir=tmp_path))
    session._page = page
    session._browser = browser
    session._playwright = playwright
    session._owns_context = False

    session.close()

    assert page.closed is True
    assert browser.close_calls == 0
    assert playwright.stop_calls == 1
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python3 -m pytest tests/test_browser_session.py -q
```

Expected: collection fails because `kkday_scraper.browser_session` does not exist.

- [ ] **Step 3: Implement attach-first browser ownership and safe probe**

Create `kkday_scraper/browser_session.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from .models import RunConfig, SessionProbe


class SessionUnavailableError(RuntimeError):
    pass


PROBE_SCRIPT = """
async ({ market }) => {
  const response = await fetch(`/api/_nuxt/member/get-member-status?t=${Date.now()}`, {
    method: "GET",
    credentials: "include",
    headers: { market }
  });
  const contentType = response.headers.get("content-type") || "";
  let data = null;
  if (contentType.includes("application/json")) {
    data = await response.json();
  }
  return {
    status: response.status,
    contentType,
    isLogin: Boolean(data && data.data && data.data.isLogin),
    currency: data && data.data && data.data.currency ? String(data.data.currency) : ""
  };
}
"""


def classify_probe(raw: dict[str, Any], page_url: str, market: str) -> SessionProbe:
    status = int(raw.get("status") or 0)
    content_type = str(raw.get("contentType") or "").lower()
    blocked = status in {401, 403} or "text/html" in content_type
    reason = "KKday 返回 403/HTML，浏览器会话需要人工验证" if blocked else None
    return SessionProbe(
        connected=True,
        api_ready=status == 200 and "json" in content_type,
        is_login=bool(raw.get("isLogin")),
        currency=str(raw.get("currency") or ""),
        market=market,
        page_url=page_url,
        block_reason=reason,
    )


class BrowserSession:
    def __init__(self, config: RunConfig, profile_dir: Path | None = None) -> None:
        self.config = config
        self.profile_dir = profile_dir or Path.home() / ".kkday_scraper" / "browser_profile"
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._owns_context = False

    @property
    def page(self) -> Page:
        if self._page is None:
            raise SessionUnavailableError("浏览器尚未连接")
        return self._page

    def connect(self, allow_launch: bool = True) -> None:
        if self._page is not None:
            return
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.connect_over_cdp(self.config.cdp_url)
            if not self._browser.contexts:
                raise SessionUnavailableError("CDP 浏览器没有可复用的默认上下文")
            self._context = self._browser.contexts[0]
            self._page = self._context.new_page()
            self._owns_context = False
        except Exception as attach_error:
            if not allow_launch:
                self.close()
                raise SessionUnavailableError(f"无法连接 CDP 浏览器：{attach_error}") from attach_error
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            try:
                self._context = self._playwright.chromium.launch_persistent_context(
                    str(self.profile_dir),
                    channel="chrome",
                    headless=False,
                    no_viewport=True,
                    locale="zh-TW",
                )
                self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
                self._owns_context = True
            except Exception as launch_error:
                self.close()
                raise SessionUnavailableError(f"无法启动专用 Chrome：{launch_error}") from launch_error

        if not self.page.url.startswith("https://www.kkday.com/"):
            self.page.goto("https://www.kkday.com/zh-tw", wait_until="domcontentloaded", timeout=60_000)

    def probe(self, market: str) -> SessionProbe:
        raw = self.page.evaluate(PROBE_SCRIPT, {"market": market})
        return classify_probe(raw, self.page.url, market)

    def close(self) -> None:
        page, context, playwright = self._page, self._context, self._playwright
        owns_context = self._owns_context
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._owns_context = False
        try:
            if owns_context and context is not None:
                context.close()
            elif page is not None:
                page.close()
        finally:
            if playwright is not None:
                playwright.stop()
```

- [ ] **Step 4: Run browser-session tests**

Run:

```bash
python3 -m pytest tests/test_browser_session.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit browser ownership**

```bash
git add kkday_scraper/browser_session.py tests/test_browser_session.py
git commit -m "feat: attach KKday scraper to a real browser session"
```

---

### Task 5: Implement Same-Origin Browser API Requests

**Files:**
- Create: `kkday_scraper/browser_api.py`
- Create: `tests/test_browser_api.py`

**Interfaces:**
- Consumes: a Playwright `Page` owned by `BrowserSession` and `RunConfig` from Task 1.
- Produces: `BrowserApiClient.get_json(path: str) -> dict`.
- Produces: `BrowserApiClient.fetch_package_calendar(...) -> dict`.
- Produces: `BrowserApiClient.fetch_items_data(...) -> dict`.
- Produces: `BrowserApiError`, `SessionBlockedError`, `SessionExpiredError`, and `ApiSchemaError`.
- Guarantees: browser fetch uses `credentials: "include"`, explicit `market`, `AbortController`, and no exported auth values.

- [ ] **Step 1: Write failing browser-API tests**

Create `tests/test_browser_api.py`:

```python
from datetime import date
import json

import pytest

from kkday_scraper.browser_api import (
    ApiSchemaError,
    BrowserApiClient,
    SessionBlockedError,
)


class FakePage:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def evaluate(self, _script: str, args: dict) -> dict:
        self.calls.append(args)
        return self.responses.pop(0)


def json_response(payload: dict, status: int = 200) -> dict:
    return {
        "status": status,
        "contentType": "application/json;charset=utf-8",
        "text": json.dumps(payload),
    }


def test_fetch_items_data_uses_verified_query_shape() -> None:
    page = FakePage([json_response({"status": 200, "message": "success", "data": {"221992": {}}})])
    client = BrowserApiClient(page, market="zh-tw", timeout_ms=30_000)

    client.fetch_items_data(
        package_id="476215",
        item_ids=("221992",),
        begin_date=date(2026, 7, 22),
        end_date=date(2026, 8, 31),
    )

    path = page.calls[0]["path"]
    assert "pkgOid=476215" in path
    assert "itemOidList=221992" in path
    assert "itemOidList%5B%5D=221992" in path
    assert "shouldInstantCalendar=false" in path
    assert page.calls[0]["market"] == "zh-tw"


def test_html_403_stops_as_session_block() -> None:
    page = FakePage([{"status": 403, "contentType": "text/html", "text": "challenge"}])
    client = BrowserApiClient(page, market="zh-tw", timeout_ms=30_000)

    with pytest.raises(SessionBlockedError):
        client.get_json("/api/_nuxt/product/fetch-product-setting?prodMid=149025")


def test_http_200_without_success_contract_is_schema_error() -> None:
    page = FakePage([json_response({"message": "unexpected"})])
    client = BrowserApiClient(page, market="zh-tw", timeout_ms=30_000)

    with pytest.raises(ApiSchemaError):
        client.get_json("/api/_nuxt/product/fetch-product-setting?prodMid=149025")
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python3 -m pytest tests/test_browser_api.py -q
```

Expected: collection fails because `kkday_scraper.browser_api` does not exist.

- [ ] **Step 3: Implement the browser-context HTTP client**

Create `kkday_scraper/browser_api.py`:

```python
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


class BrowserApiClient:
    def __init__(self, page: PageLike, market: str, timeout_ms: int) -> None:
        self.page = page
        self.market = market
        self.timeout_ms = timeout_ms

    def get_json(self, path: str) -> dict:
        try:
            raw = self.page.evaluate(
                FETCH_SCRIPT,
                {"path": path, "market": self.market, "timeoutMs": self.timeout_ms},
            )
        except Exception as exc:
            raise BrowserApiError(f"浏览器内请求失败：{type(exc).__name__}: {exc}") from exc
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
        if not isinstance(payload, dict) or payload.get("message") != "success" or "data" not in payload:
            raise ApiSchemaError("KKday API 缺少 message=success/data 契约")
        return payload

    def fetch_package_calendar(self, product_id: str, begin_date: date, end_date: date) -> dict:
        return self.get_json(
            "/api/_nuxt/product/fetch-packages-price-calendar"
            f"?beginDate={begin_date.isoformat()}"
            f"&endDate={end_date.isoformat()}"
            f"&prodOid={quote(product_id)}"
            "&previewToken"
        )

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
        repeated = "&".join(f"itemOidList%5B%5D={quote(item_id)}" for item_id in item_ids)
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
```

- [ ] **Step 4: Run browser-API tests**

Run:

```bash
python3 -m pytest tests/test_browser_api.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit the API client**

```bash
git add kkday_scraper/browser_api.py tests/test_browser_api.py
git commit -m "feat: replay KKday price APIs inside browser context"
```

---

### Task 6: Assemble One Product from Nuxt State and Interface Responses

**Files:**
- Create: `tests/fixtures/product_snapshot_149025.json`
- Create: `kkday_scraper/product_scraper.py`
- Create: `tests/test_product_scraper.py`

**Interfaces:**
- Consumes: `BrowserApiClient`, `SchemaDriftError`, `parse_item_payload`, `package_minimum`, `validate_package_minimum`, and Task 1 models.
- Produces: `extract_product_snapshot(page, url: str) -> ProductSnapshot`.
- Produces: `ProductScraper.scrape(input_item: InputItem, probe: SessionProbe, config: RunConfig) -> ProductResult`.
- Guarantees: one navigation per product, one calendar call per product, one item-data call per package, finite API retry, package-level continuation, and no SKU clicks.

- [ ] **Step 1: Add a sanitized product snapshot fixture**

Create `tests/fixtures/product_snapshot_149025.json`:

```json
{
  "productId": "149025",
  "url": "https://www.kkday.com/zh-tw/product/149025-example",
  "name": "日本 eSIM｜SoftBank 5G 高速無限流量",
  "packages": [
    {
      "packageId": "476215",
      "name": "【50% OFF】日本網卡｜SoftBank 每日/無限流量 eSIM",
      "itemIds": ["221992"],
      "description": ""
    },
    {
      "packageId": "1982144",
      "name": "【50% OFF】日本網卡｜SoftBank 總量 eSIM",
      "itemIds": ["1727921"],
      "description": ""
    }
  ]
}
```

- [ ] **Step 2: Write failing product assembly tests**

Create `tests/test_product_scraper.py`:

```python
import json
from datetime import date
from pathlib import Path

from kkday_scraper.models import InputItem, RunConfig, SessionProbe
from kkday_scraper.product_scraper import ProductScraper, extract_product_snapshot


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakePage:
    def __init__(self, snapshot: dict) -> None:
        self.snapshot = snapshot
        self.goto_calls: list[str] = []
        self.url = snapshot["url"]

    def goto(self, url: str, **_kwargs) -> None:
        self.goto_calls.append(url)
        self.url = url

    def wait_for_function(self, _expression: str, **_kwargs) -> None:
        return None

    def evaluate(self, _expression: str) -> dict:
        return self.snapshot


class FakeApi:
    def __init__(self) -> None:
        self.item_calls: list[str] = []

    def fetch_package_calendar(self, _product_id, _begin, _end) -> dict:
        return load_fixture("package_calendar_149025.json")

    def fetch_items_data(self, package_id, _item_ids, _begin, _end) -> dict:
        self.item_calls.append(package_id)
        name = "items_data_476215.json" if package_id == "476215" else "items_data_1982144.json"
        return load_fixture(name)


def test_snapshot_reads_packages_without_clicking() -> None:
    page = FakePage(load_fixture("product_snapshot_149025.json"))
    snapshot = extract_product_snapshot(page, page.url)

    assert snapshot.product_id == "149025"
    assert [package.package_id for package in snapshot.packages] == ["476215", "1982144"]
    assert snapshot.packages[0].item_ids == ("221992",)


def test_scrape_calls_each_package_once_and_returns_available_prices(tmp_path: Path) -> None:
    page = FakePage(load_fixture("product_snapshot_149025.json"))
    api = FakeApi()
    scraper = ProductScraper(page, api, sleep=lambda _seconds: None, uniform=lambda low, _high: low)
    config = RunConfig(usage_date=date(2026, 7, 22), output_dir=tmp_path)
    probe = SessionProbe(True, True, True, "KRW", "zh-tw", page.url)

    result = scraper.scrape(InputItem(url=page.url), probe, config)

    assert api.item_calls == ["476215", "1982144"]
    assert len(result.rows) == 3
    assert len([row for row in result.rows if row.available]) == 2
    assert all(row.sale_price is not None for row in result.rows if row.available)
    assert result.failures == ()


def test_scrape_stop_gate_prevents_next_package_request(tmp_path: Path) -> None:
    page = FakePage(load_fixture("product_snapshot_149025.json"))
    api = FakeApi()
    checks = iter((True, True, True, False))
    scraper = ProductScraper(
        page,
        api,
        sleep=lambda _seconds: None,
        uniform=lambda low, _high: low,
        continue_run=lambda: next(checks),
    )
    config = RunConfig(usage_date=date(2026, 7, 22), output_dir=tmp_path)
    probe = SessionProbe(True, True, True, "KRW", "zh-tw", page.url)

    result = scraper.scrape(InputItem(url=page.url), probe, config)

    assert api.item_calls == ["476215"]
    assert len(result.rows) == 2
    assert result.warnings[-1] == "用户在套餐之间停止"
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```bash
python3 -m pytest tests/test_product_scraper.py -q
```

Expected: collection fails because `kkday_scraper.product_scraper` does not exist.

- [ ] **Step 4: Implement product snapshot and assembly**

Create `kkday_scraper/product_scraper.py`:

```python
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from random import uniform
from time import sleep
from typing import Callable, Protocol

from .browser_api import BrowserApiClient, BrowserApiError, SessionBlockedError, SessionExpiredError
from .models import (
    FailureKind,
    FailureRecord,
    InputItem,
    PackageRef,
    PriceStatus,
    ProductResult,
    ProductSnapshot,
    RunConfig,
    SessionProbe,
)
from .sku_parser import SchemaDriftError, package_minimum, parse_item_payload, validate_package_minimum


SNAPSHOT_SCRIPT = """
() => {
  const option = window.__NUXT__ && window.__NUXT__.pinia && window.__NUXT__.pinia["option-section"];
  if (!option || !option.packages) return null;
  const match = location.pathname.match(/\/product\/([A-Za-z0-9_-]+)/);
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
    def goto(self, url: str, **kwargs) -> None: ...
    def wait_for_function(self, expression: str, **kwargs) -> None: ...
    def evaluate(self, expression: str) -> dict | None: ...


def extract_product_snapshot(page: PageLike, url: str) -> ProductSnapshot:
    raw = page.evaluate(SNAPSHOT_SCRIPT)
    if not raw or not raw.get("productId") or not raw.get("packages"):
        raise SchemaDriftError("Nuxt option-section 缺少商品或套餐结构")
    packages = tuple(
        PackageRef(
            package_id=str(package["packageId"]),
            name=str(package.get("name") or ""),
            item_ids=tuple(str(item_id) for item_id in package.get("itemIds", [])),
            description=str(package.get("description") or ""),
        )
        for package in raw["packages"]
    )
    if any(not package.item_ids for package in packages):
        raise SchemaDriftError("Nuxt 套餐缺少 item ID")
    return ProductSnapshot(
        product_id=str(raw["productId"]),
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
    ) -> None:
        self.page = page
        self.api = api
        self.sleep = sleep
        self.uniform = uniform
        self.continue_run = continue_run

    def _read_with_retry(self, operation: Callable[[], dict], config: RunConfig) -> dict:
        attempts = len(config.request_retry_delays) + 1
        for attempt in range(attempts):
            try:
                return operation()
            except (SessionBlockedError, SessionExpiredError):
                raise
            except BrowserApiError:
                if attempt == attempts - 1:
                    raise
                self.sleep(config.request_retry_delays[attempt])
        raise AssertionError("unreachable")

    def scrape(self, input_item: InputItem, probe: SessionProbe, config: RunConfig) -> ProductResult:
        failures: list[FailureRecord] = []
        warnings: list[str] = []
        rows = []
        if not probe.api_ready:
            return ProductResult(
                input_item,
                None,
                (),
                (FailureRecord(FailureKind.SESSION_BLOCKED, input_item.url, "probe", probe.block_reason or "会话不可用", False, input_item.input_order),),
            )
        try:
            self.page.goto(input_item.url, wait_until="domcontentloaded", timeout=60_000)
            self.page.wait_for_function(
                "() => Boolean(window.__NUXT__?.pinia?.['option-section']?.packages)",
                timeout=45_000,
            )
            snapshot = extract_product_snapshot(self.page, input_item.url)
        except Exception as exc:
            return ProductResult(
                input_item,
                None,
                (),
                (FailureRecord(FailureKind.NAVIGATION, input_item.url, "snapshot", str(exc), True, input_item.input_order),),
            )

        end_date = config.usage_date + timedelta(days=40)
        if not self.continue_run():
            return ProductResult(input_item, snapshot, (), warnings=("用户在价格日历请求前停止",))
        try:
            calendar = self._read_with_retry(
                lambda: self.api.fetch_package_calendar(snapshot.product_id, config.usage_date, end_date),
                config,
            )
        except (SessionBlockedError, SessionExpiredError):
            raise
        except Exception as exc:
            return ProductResult(
                input_item,
                snapshot,
                (),
                (FailureRecord(FailureKind.API, input_item.url, "package_calendar", str(exc), True, input_item.input_order),),
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
                expected = package_minimum(calendar, package.package_id, config.usage_date)
                valid, reason = validate_package_minimum(package_rows, expected)
                if not valid:
                    warnings.append(f"套餐 {package.package_id}: {reason}")
                    status = PriceStatus.MISSING if "缺少价格" in reason else PriceStatus.MINIMUM_MISMATCH
                    package_rows = [
                        replace(row, price_status=status, note=reason) if row.available else row
                        for row in package_rows
                    ]
                    failures.append(
                        FailureRecord(
                            FailureKind.MISSING_PRICE if status is PriceStatus.MISSING else FailureKind.PRICE_MISMATCH,
                            input_item.url,
                            f"package:{package.package_id}",
                            reason,
                            True,
                            input_item.input_order,
                        )
                    )
                rows.extend(package_rows)
            except (SessionBlockedError, SessionExpiredError):
                raise
            except SchemaDriftError as exc:
                failures.append(FailureRecord(FailureKind.SCHEMA, input_item.url, f"package:{package.package_id}", str(exc), False, input_item.input_order))
            except Exception as exc:
                failures.append(FailureRecord(FailureKind.API, input_item.url, f"package:{package.package_id}", str(exc), True, input_item.input_order))
            if package_index + 1 < len(snapshot.packages):
                self.sleep(self.uniform(*config.package_delay_range))

        return ProductResult(input_item, snapshot, tuple(rows), tuple(failures), tuple(warnings))
```

- [ ] **Step 5: Run product assembly tests**

Run:

```bash
python3 -m pytest tests/test_product_scraper.py -q
```

Expected: `3 passed`.

- [ ] **Step 6: Commit product assembly**

```bash
git add kkday_scraper/product_scraper.py tests/fixtures/product_snapshot_149025.json tests/test_product_scraper.py
git commit -m "feat: assemble KKday products from Nuxt and API data"
```

---

### Task 7: Add the One-Worker Batch State Machine

**Files:**
- Create: `kkday_scraper/task_runner.py`
- Create: `tests/test_task_runner.py`

**Interfaces:**
- Consumes: `BrowserSession`, `BrowserApiClient`, `ProductScraper`, Task 1 models, and an injected checkpoint writer.
- Produces: `RunControl.pause()`, `RunControl.resume()`, `RunControl.stop()`, and `RunControl.wait()`.
- Produces: `TaskRunner.run(items, config, control, reporter, checkpoint) -> RunResult`.
- Produces: `WorkerService`, a long-lived single background thread that owns Playwright for its entire lifetime.
- Guarantees: GUI thread never touches Playwright objects; 401/403 blocks the batch; trusted partial products are checkpointed after every product.

- [ ] **Step 1: Write failing runner tests**

Create `tests/test_task_runner.py`:

```python
from datetime import date
from pathlib import Path

from kkday_scraper.browser_api import SessionBlockedError
from kkday_scraper.models import (
    EventKind,
    InputItem,
    ProductResult,
    RunConfig,
    RunPhase,
    SessionProbe,
)
from kkday_scraper.task_runner import RunControl, TaskRunner


class FakeSession:
    def __init__(self, blocked_on_probe: int | None = None) -> None:
        self.probe_calls = 0
        self.blocked_on_probe = blocked_on_probe
        self.page = object()

    def probe(self, market: str) -> SessionProbe:
        self.probe_calls += 1
        if self.blocked_on_probe == self.probe_calls:
            return SessionProbe(True, False, True, "KRW", market, "https://www.kkday.com", "blocked")
        return SessionProbe(True, True, True, "KRW", market, "https://www.kkday.com")


class FakeScraper:
    def __init__(self, blocked_url: str | None = None) -> None:
        self.blocked_url = blocked_url
        self.calls: list[str] = []

    def scrape(self, item: InputItem, _probe: SessionProbe, _config: RunConfig) -> ProductResult:
        self.calls.append(item.url)
        if item.url == self.blocked_url:
            raise SessionBlockedError("403")
        return ProductResult(item, None, ())


def test_runner_checkpoints_after_each_product(tmp_path: Path) -> None:
    items = [
        InputItem("https://www.kkday.com/zh-tw/product/1-a", input_order=0),
        InputItem("https://www.kkday.com/zh-tw/product/2-b", input_order=1),
    ]
    session = FakeSession()
    scraper = FakeScraper()
    checkpoints: list[int] = []
    events = []
    runner = TaskRunner(session, lambda _page, _config, _continue: scraper, sleep=lambda _seconds: None, uniform=lambda low, _high: low)

    result = runner.run(
        items,
        RunConfig(date(2026, 7, 22), tmp_path),
        RunControl(),
        events.append,
        lambda products, _final: checkpoints.append(len(products)) or None,
    )

    assert scraper.calls == [items[0].url, items[1].url]
    assert checkpoints == [1, 2, 2]
    assert result.stopped is False
    assert events[-1].kind is EventKind.FINISHED
    assert events[-1].phase is RunPhase.COMPLETED


def test_runner_stops_batch_on_session_block_and_keeps_partial_result(tmp_path: Path) -> None:
    first = InputItem("https://www.kkday.com/zh-tw/product/1-a", input_order=0)
    second = InputItem("https://www.kkday.com/zh-tw/product/2-b", input_order=1)
    third = InputItem("https://www.kkday.com/zh-tw/product/3-c", input_order=2)
    session = FakeSession()
    scraper = FakeScraper(blocked_url=second.url)
    events = []
    runner = TaskRunner(session, lambda _page, _config, _continue: scraper, sleep=lambda _seconds: None, uniform=lambda low, _high: low)

    result = runner.run(
        [first, second, third],
        RunConfig(date(2026, 7, 22), tmp_path),
        RunControl(),
        events.append,
        lambda _products, _final: None,
    )

    assert scraper.calls == [first.url, second.url]
    assert len(result.products) == 1
    assert events[-1].phase is RunPhase.BLOCKED


def test_stop_before_next_product_is_cooperative(tmp_path: Path) -> None:
    control = RunControl()
    control.stop()
    runner = TaskRunner(FakeSession(), lambda _page, _config, _continue: FakeScraper(), sleep=lambda _seconds: None)

    result = runner.run(
        [InputItem("https://www.kkday.com/zh-tw/product/1-a")],
        RunConfig(date(2026, 7, 22), tmp_path),
        control,
        lambda _event: None,
        lambda _products, _final: None,
    )

    assert result.products == ()
    assert result.stopped is True
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python3 -m pytest tests/test_task_runner.py -q
```

Expected: collection fails because `kkday_scraper.task_runner` does not exist.

- [ ] **Step 3: Implement cooperative runner and long-lived browser worker**

Create `kkday_scraper/task_runner.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from queue import Queue
from random import uniform
from threading import Event, Thread
from time import sleep
from typing import Callable, Protocol

from .browser_api import BrowserApiClient, SessionBlockedError, SessionExpiredError
from .browser_session import BrowserSession
from .models import (
    AppEvent,
    EventKind,
    FailureKind,
    FailureRecord,
    InputItem,
    ProductResult,
    RunConfig,
    RunPhase,
    RunResult,
)
from .product_scraper import ProductScraper


Reporter = Callable[[AppEvent], None]
Checkpoint = Callable[[tuple[ProductResult, ...], bool], object | None]


class SessionLike(Protocol):
    page: object
    def connect(self, allow_launch: bool = True) -> None: ...
    def probe(self, market: str): ...
    def close(self) -> None: ...


class RunControl:
    def __init__(self) -> None:
        self._running = Event()
        self._running.set()
        self._stopped = Event()

    @property
    def stopped(self) -> bool:
        return self._stopped.is_set()

    def pause(self) -> None:
        self._running.clear()

    def resume(self) -> None:
        self._running.set()

    def stop(self) -> None:
        self._stopped.set()
        self._running.set()

    def wait(self) -> bool:
        while not self._stopped.is_set():
            if self._running.wait(timeout=0.2):
                return True
        return False


class TaskRunner:
    def __init__(
        self,
        session: SessionLike,
        scraper_factory: Callable[[object, RunConfig, Callable[[], bool]], ProductScraper] | None = None,
        *,
        sleep: Callable[[float], None] = sleep,
        uniform: Callable[[float, float], float] = uniform,
    ) -> None:
        self.session = session
        self.sleep = sleep
        self.uniform = uniform
        self.scraper_factory = scraper_factory or self._default_scraper

    def _default_scraper(self, page: object, config: RunConfig, continue_run: Callable[[], bool]) -> ProductScraper:
        api = BrowserApiClient(page, config.market, config.request_timeout_ms)
        return ProductScraper(page, api, continue_run=continue_run)

    def run(
        self,
        items: list[InputItem],
        config: RunConfig,
        control: RunControl,
        reporter: Reporter,
        checkpoint: Checkpoint,
    ) -> RunResult:
        started = datetime.now()
        products: list[ProductResult] = []
        blocked = False
        reporter(AppEvent(EventKind.PHASE, "开始抓取", RunPhase.RUNNING, 0, len(items)))
        scraper = self.scraper_factory(self.session.page, config, control.wait)
        for index, item in enumerate(items):
            if control.stopped or not control.wait():
                break
            reporter(AppEvent(EventKind.PROGRESS, f"处理 {item.url}", RunPhase.RUNNING, index + 1, len(items)))
            probe = self.session.probe(config.market)
            if not probe.api_ready:
                blocked = True
                reporter(AppEvent(EventKind.FAILURE, probe.block_reason or "浏览器会话不可用", RunPhase.BLOCKED, index + 1, len(items)))
                break
            try:
                product = scraper.scrape(item, probe, config)
            except (SessionBlockedError, SessionExpiredError) as exc:
                blocked = True
                reporter(AppEvent(EventKind.FAILURE, str(exc), RunPhase.BLOCKED, index + 1, len(items)))
                break
            except Exception as exc:
                product = ProductResult(
                    item,
                    None,
                    (),
                    (FailureRecord(FailureKind.API, item.url, "product", str(exc), True, item.input_order),),
                )
            products.append(product)
            checkpoint(tuple(products), False)
            reporter(AppEvent(EventKind.PRODUCT_RESULT, f"商品完成：{item.url}", RunPhase.RUNNING, index + 1, len(items), product))
            if index + 1 < len(items) and not control.stopped:
                self.sleep(self.uniform(*config.product_delay_range))

        output_path = checkpoint(tuple(products), True)
        phase = RunPhase.BLOCKED if blocked else RunPhase.COMPLETED
        result = RunResult(
            products=tuple(products),
            output_path=output_path if hasattr(output_path, "suffix") else None,
            started_at=started,
            finished_at=datetime.now(),
            stopped=control.stopped,
        )
        reporter(AppEvent(EventKind.FINISHED, "任务已停止" if control.stopped else "任务完成", phase, len(products), len(items), result))
        return result


class WorkerCommandKind(str, Enum):
    CONNECT = "connect"
    RUN = "run"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True)
class WorkerCommand:
    kind: WorkerCommandKind
    config: RunConfig | None = None
    items: tuple[InputItem, ...] = ()


class WorkerService:
    def __init__(
        self,
        reporter: Reporter,
        checkpoint_factory: Callable[[RunConfig], Checkpoint],
        session_factory: Callable[[RunConfig], SessionLike] = BrowserSession,
    ) -> None:
        self.reporter = reporter
        self.checkpoint_factory = checkpoint_factory
        self.session_factory = session_factory
        self.commands: Queue[WorkerCommand] = Queue()
        self.control = RunControl()
        self._session: SessionLike | None = None
        self._thread = Thread(target=self._loop, name="kkday-browser-worker", daemon=True)
        self._thread.start()

    def connect(self, config: RunConfig) -> None:
        self.commands.put(WorkerCommand(WorkerCommandKind.CONNECT, config))

    def run(self, items: list[InputItem], config: RunConfig) -> None:
        self.control = RunControl()
        self.commands.put(WorkerCommand(WorkerCommandKind.RUN, config, tuple(items)))

    def pause(self) -> None:
        self.control.pause()
        self.reporter(AppEvent(EventKind.PHASE, "已暂停", RunPhase.PAUSED))

    def resume(self) -> None:
        self.control.resume()
        self.reporter(AppEvent(EventKind.PHASE, "继续运行", RunPhase.RUNNING))

    def stop(self) -> None:
        self.control.stop()
        self.reporter(AppEvent(EventKind.PHASE, "正在停止", RunPhase.STOPPING))

    def shutdown(self) -> None:
        self.stop()
        self.commands.put(WorkerCommand(WorkerCommandKind.SHUTDOWN))

    def _loop(self) -> None:
        while True:
            command = self.commands.get()
            if command.kind is WorkerCommandKind.SHUTDOWN:
                if self._session is not None:
                    self._session.close()
                return
            if command.config is None:
                continue
            if command.kind is WorkerCommandKind.CONNECT:
                try:
                    if self._session is not None:
                        self._session.close()
                    self._session = self.session_factory(command.config)
                    self.reporter(AppEvent(EventKind.PHASE, "正在连接浏览器", RunPhase.CONNECTING))
                    self._session.connect()
                    probe = self._session.probe(command.config.market)
                    phase = RunPhase.READY if probe.api_ready else RunPhase.BLOCKED
                    self.reporter(AppEvent(EventKind.PHASE, "浏览器会话可用" if probe.api_ready else probe.block_reason or "会话不可用", phase, payload=probe))
                except Exception as exc:
                    self.reporter(AppEvent(EventKind.FAILURE, f"浏览器连接失败：{exc}", RunPhase.FAILED))
            elif command.kind is WorkerCommandKind.RUN:
                if self._session is None:
                    self.reporter(AppEvent(EventKind.FAILURE, "请先连接浏览器", RunPhase.FAILED))
                    continue
                runner = TaskRunner(self._session)
                runner.run(list(command.items), command.config, self.control, self.reporter, self.checkpoint_factory(command.config))
```

- [ ] **Step 4: Run runner tests**

Run:

```bash
python3 -m pytest tests/test_task_runner.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit the batch state machine**

```bash
git add kkday_scraper/task_runner.py tests/test_task_runner.py
git commit -m "feat: add finite single-worker KKday task runner"
```

---

### Task 8: Add Atomic Partial and Final Exports

**Files:**
- Create: `kkday_scraper/exporter.py`
- Create: `tests/test_exporter.py`

**Interfaces:**
- Consumes: `ProductResult`, `SkuRow`, `FailureRecord`, and `RunConfig`.
- Produces: `RunExporter(config).checkpoint(products, final) -> Path`.
- Produces workbook sheets `可售SKU`, `失败与警告`, and `运行摘要`.
- Produces atomic `run_summary.json` and optional `failures.jsonl` without secrets.
- Guarantees: each checkpoint replaces the previous valid workbook only after the new workbook saves successfully.

- [ ] **Step 1: Write failing export tests**

Create `tests/test_exporter.py`:

```python
from datetime import date
from decimal import Decimal
from pathlib import Path

import openpyxl

from kkday_scraper.exporter import RunExporter
from kkday_scraper.models import (
    FailureKind,
    FailureRecord,
    InputItem,
    PriceStatus,
    ProductResult,
    RunConfig,
    SkuRow,
)


def make_product() -> ProductResult:
    item = InputItem("https://www.kkday.com/zh-tw/product/149025-example", vendor="TSIM 網址")
    row = SkuRow(
        vendor=item.vendor,
        input_order=0,
        product_id="149025",
        product_url=item.url,
        product_name="日本 eSIM",
        package_id="476215",
        package_name="每日/无限流量",
        item_id="221992",
        sku_id="sku-1",
        usage_date=date(2026, 7, 22),
        options=("500MB/日", "1 日"),
        available=True,
        currency="KRW",
        sale_price=Decimal("711"),
        official_price=None,
        price_source="single_price.fullday",
        price_status=PriceStatus.TRUSTED,
    )
    failure = FailureRecord(FailureKind.API, item.url, "package:2", "HTTP 500", True)
    return ProductResult(item, None, (row,), (failure,), ("一个警告",))


def test_checkpoint_writes_stable_workbook_and_failure_ledger(tmp_path: Path) -> None:
    config = RunConfig(date(2026, 7, 22), tmp_path)
    exporter = RunExporter(config, run_id="20260722_120000")

    output = exporter.checkpoint((make_product(),), final=True)

    assert output.exists()
    workbook = openpyxl.load_workbook(output, data_only=True)
    assert workbook.sheetnames == ["可售SKU", "失败与警告", "运行摘要"]
    sheet = workbook["可售SKU"]
    headers = [cell.value for cell in sheet[1]]
    assert headers[:8] == ["厂商", "输入序号", "商品ID", "URL", "商品名称", "套餐ID", "套餐名称", "ItemID"]
    assert sheet["M2"].value == 711
    assert exporter.summary_path.exists()
    assert exporter.failures_path.exists()


def test_checkpoint_omits_unavailable_rows_by_default(tmp_path: Path) -> None:
    product = make_product()
    unavailable = product.rows[0].__class__(
        **{**product.rows[0].__dict__, "sku_id": "closed", "available": False, "price_status": PriceStatus.UNAVAILABLE}
    )
    product = ProductResult(product.input_item, None, product.rows + (unavailable,))
    exporter = RunExporter(RunConfig(date(2026, 7, 22), tmp_path), run_id="20260722_120001")

    output = exporter.checkpoint((product,), final=False)

    workbook = openpyxl.load_workbook(output, data_only=True)
    assert workbook["可售SKU"].max_row == 2
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python3 -m pytest tests/test_exporter.py -q
```

Expected: collection fails because `kkday_scraper.exporter` does not exist.

- [ ] **Step 3: Implement atomic workbook and ledgers**

Create `kkday_scraper/exporter.py`:

```python
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import openpyxl
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from .models import ProductResult, RunConfig, SkuRow


BASE_FIELDS = [
    "厂商", "输入序号", "商品ID", "URL", "商品名称", "套餐ID", "套餐名称", "ItemID", "SKU ID",
    "使用日期", "规格组合", "货币", "当前价格", "原价", "价格来源", "价格状态", "抓取备注", "抓取时间",
]


def excel_value(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


class RunExporter:
    def __init__(self, config: RunConfig, run_id: str | None = None) -> None:
        self.config = config
        self.run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = config.output_dir / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.output_path = self.run_dir / "kkday_price_results.xlsx"
        self.summary_path = self.run_dir / "run_summary.json"
        self.failures_path = self.run_dir / "failures.jsonl"

    def _row_values(self, row: SkuRow) -> list:
        return [
            row.vendor,
            row.input_order + 1,
            row.product_id,
            row.product_url,
            row.product_name,
            row.package_id,
            row.package_name,
            row.item_id,
            row.sku_id,
            row.usage_date.isoformat(),
            row.option_text,
            row.currency,
            excel_value(row.sale_price),
            excel_value(row.official_price),
            row.price_source,
            row.price_status.value,
            row.note,
            row.captured_at.isoformat(timespec="seconds"),
        ]

    def checkpoint(self, products: tuple[ProductResult, ...], final: bool) -> Path:
        rows = [row for product in products for row in product.rows]
        if not self.config.include_unavailable:
            rows = [row for row in rows if row.available]
        failures = [failure for product in products for failure in product.failures]
        warnings = [(product.input_item.url, warning) for product in products for warning in product.warnings]

        workbook = openpyxl.Workbook()
        sku_sheet = workbook.active
        sku_sheet.title = "可售SKU"
        sku_sheet.append(BASE_FIELDS)
        for row in rows:
            sku_sheet.append(self._row_values(row))

        failure_sheet = workbook.create_sheet("失败与警告")
        failure_sheet.append(["类型", "URL", "阶段", "消息", "可重试", "时间"])
        for failure in failures:
            failure_sheet.append([
                failure.kind.value,
                failure.url,
                failure.stage,
                failure.message,
                "是" if failure.retryable else "否",
                failure.captured_at.isoformat(timespec="seconds"),
            ])
        for url, warning in warnings:
            failure_sheet.append(["warning", url, "quality", warning, "否", ""])

        summary_sheet = workbook.create_sheet("运行摘要")
        summary_sheet.append(["字段", "值"])
        summary_sheet.append(["运行ID", self.run_id])
        summary_sheet.append(["使用日期", self.config.usage_date.isoformat()])
        summary_sheet.append(["商品完成数", len(products)])
        summary_sheet.append(["导出SKU数", len(rows)])
        summary_sheet.append(["失败数", len(failures)])
        summary_sheet.append(["状态", "final" if final else "partial"])

        for sheet in workbook.worksheets:
            for cell in sheet[1]:
                cell.font = Font(bold=True)
            for column in sheet.columns:
                width = min(max(max(len(str(cell.value or "")) for cell in column) + 2, 10), 70)
                sheet.column_dimensions[get_column_letter(column[0].column)].width = width

        with tempfile.NamedTemporaryFile(dir=self.run_dir, prefix=".workbook-", suffix=".xlsx", delete=False) as handle:
            temp_workbook = Path(handle.name)
        try:
            workbook.save(temp_workbook)
            os.replace(temp_workbook, self.output_path)
        finally:
            temp_workbook.unlink(missing_ok=True)

        summary = {
            "run_id": self.run_id,
            "usage_date": self.config.usage_date.isoformat(),
            "status": "final" if final else "partial",
            "product_count": len(products),
            "row_count": len(rows),
            "failure_count": len(failures),
            "output": str(self.output_path),
        }
        self._atomic_text(self.summary_path, json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        if failures:
            lines = [
                json.dumps(
                    {
                        "kind": failure.kind.value,
                        "url": failure.url,
                        "stage": failure.stage,
                        "message": failure.message,
                        "retryable": failure.retryable,
                        "captured_at": failure.captured_at.isoformat(timespec="seconds"),
                    },
                    ensure_ascii=False,
                )
                for failure in failures
            ]
            self._atomic_text(self.failures_path, "\n".join(lines) + "\n")
        else:
            self.failures_path.unlink(missing_ok=True)
        return self.output_path

    def _atomic_text(self, path: Path, content: str) -> None:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}-", mode="w", encoding="utf-8", delete=False) as handle:
            handle.write(content)
            temporary = Path(handle.name)
        os.replace(temporary, path)
```

- [ ] **Step 4: Run export tests**

Run:

```bash
python3 -m pytest tests/test_exporter.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit durable exports**

```bash
git add kkday_scraper/exporter.py tests/test_exporter.py
git commit -m "feat: export atomic KKday SKU workbooks"
```

---

### Task 9: Rebuild the Tkinter GUI Around Typed Worker Events

**Files:**
- Create: `kkday_scraper/gui_state.py`
- Create: `kkday_scraper/gui.py`
- Create: `tests/test_gui_state.py`
- Modify: `kkday_get_scoreandprice.pyw`

**Interfaces:**
- Consumes: Task 1 models, Task 2 input loaders, `WorkerService`, and `RunExporter`.
- Produces: `button_policy(phase, has_inputs, has_results) -> ButtonPolicy`.
- Produces: `KKdayScraperApp`, which owns Tk widgets and a thread-safe `Queue[AppEvent]` but no browser/page/API object.
- Produces: compatibility launcher `kkday_get_scoreandprice.pyw -> kkday_scraper.gui.main()`.
- Guarantees: all widget mutations occur on the Tk main thread; all Playwright operations remain in `WorkerService`.

- [ ] **Step 1: Write failing GUI state tests**

Create `tests/test_gui_state.py`:

```python
from kkday_scraper.gui_state import button_policy
from kkday_scraper.models import RunPhase


def test_idle_policy_allows_input_and_connect_only() -> None:
    policy = button_policy(RunPhase.IDLE, has_inputs=True, has_results=False)

    assert policy.connect is True
    assert policy.edit_inputs is True
    assert policy.start is False
    assert policy.pause is False
    assert policy.stop is False


def test_ready_policy_requires_inputs_to_start() -> None:
    assert button_policy(RunPhase.READY, False, False).start is False
    assert button_policy(RunPhase.READY, True, False).start is True


def test_running_and_paused_policies_are_mutually_consistent() -> None:
    running = button_policy(RunPhase.RUNNING, True, True)
    paused = button_policy(RunPhase.PAUSED, True, True)

    assert (running.pause, running.resume, running.stop) == (True, False, True)
    assert (paused.pause, paused.resume, paused.stop) == (False, True, True)
    assert running.edit_inputs is False
    assert paused.edit_inputs is False
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python3 -m pytest tests/test_gui_state.py -q
```

Expected: collection fails because `kkday_scraper.gui_state` does not exist.

- [ ] **Step 3: Implement the pure GUI policy**

Create `kkday_scraper/gui_state.py`:

```python
from dataclasses import dataclass

from .models import RunPhase


@dataclass(frozen=True)
class ButtonPolicy:
    connect: bool
    probe: bool
    edit_inputs: bool
    start: bool
    pause: bool
    resume: bool
    stop: bool
    export: bool


def button_policy(phase: RunPhase, has_inputs: bool, has_results: bool) -> ButtonPolicy:
    busy = phase in {RunPhase.CONNECTING, RunPhase.RUNNING, RunPhase.PAUSED, RunPhase.STOPPING}
    return ButtonPolicy(
        connect=phase in {RunPhase.IDLE, RunPhase.READY, RunPhase.BLOCKED, RunPhase.COMPLETED, RunPhase.FAILED},
        probe=phase in {RunPhase.READY, RunPhase.BLOCKED},
        edit_inputs=not busy,
        start=phase is RunPhase.READY and has_inputs,
        pause=phase is RunPhase.RUNNING,
        resume=phase is RunPhase.PAUSED,
        stop=phase in {RunPhase.RUNNING, RunPhase.PAUSED},
        export=has_results and phase not in {RunPhase.CONNECTING, RunPhase.STOPPING},
    )
```

- [ ] **Step 4: Run GUI state tests**

Run:

```bash
python3 -m pytest tests/test_gui_state.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Implement the complete ttk application shell**

Create `kkday_scraper/gui.py`:

```python
from __future__ import annotations

import platform
import queue
import subprocess
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .exporter import RunExporter
from .gui_state import button_policy
from .inputs import deduplicate_inputs, load_manual_urls, load_txt, load_vendor_excel
from .models import AppEvent, EventKind, InputItem, ProductResult, RunConfig, RunPhase, RunResult, SessionProbe
from .task_runner import WorkerService


class KKdayScraperApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("KKday SKU 价格抓取工具 2.0")
        self.root.geometry("1120x780")
        self.root.minsize(940, 680)
        self.phase = RunPhase.IDLE
        self.inputs: list[InputItem] = []
        self.last_result: RunResult | None = None
        self.last_output: Path | None = None
        self.events: queue.Queue[AppEvent] = queue.Queue()
        self.worker = WorkerService(self.events.put, self._checkpoint_factory)

        self.date_var = tk.StringVar(value=date.today().isoformat())
        self.market_var = tk.StringVar(value="zh-tw")
        self.port_var = tk.StringVar(value="9222")
        self.output_var = tk.StringVar(value=str(Path.home() / "Downloads" / "KKday_scraping"))
        self.session_var = tk.StringVar(value="未连接")
        self.currency_var = tk.StringVar(value="—")
        self.progress_var = tk.StringVar(value="0 / 0")
        self.status_var = tk.StringVar(value="就绪")
        self.pause_text = tk.StringVar(value="暂停")

        self._build()
        self._apply_policy()
        self.root.after(100, self._poll_events)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        session = ttk.LabelFrame(outer, text="浏览器会话", padding=10)
        session.pack(fill=tk.X)
        ttk.Label(session, text="CDP 端口").grid(row=0, column=0, sticky="w")
        ttk.Entry(session, textvariable=self.port_var, width=9).grid(row=0, column=1, padx=(6, 14))
        ttk.Label(session, text="市场").grid(row=0, column=2, sticky="w")
        ttk.Combobox(session, textvariable=self.market_var, values=("zh-tw",), state="readonly", width=9).grid(row=0, column=3, padx=(6, 14))
        self.connect_button = ttk.Button(session, text="连接 / 重新检测", command=self._connect)
        self.connect_button.grid(row=0, column=4, padx=(0, 14))
        ttk.Label(session, text="状态：").grid(row=0, column=5)
        ttk.Label(session, textvariable=self.session_var).grid(row=0, column=6, sticky="w")
        ttk.Label(session, text="币种：").grid(row=0, column=7, padx=(18, 0))
        ttk.Label(session, textvariable=self.currency_var).grid(row=0, column=8, sticky="w")

        input_frame = ttk.LabelFrame(outer, text="任务输入", padding=10)
        input_frame.pack(fill=tk.X, pady=(10, 0))
        self.manual_text = tk.Text(input_frame, height=3, wrap=tk.NONE)
        self.manual_text.grid(row=0, column=0, columnspan=7, sticky="ew")
        input_frame.columnconfigure(0, weight=1)
        self.add_button = ttk.Button(input_frame, text="添加 URL", command=self._add_manual)
        self.add_button.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.txt_button = ttk.Button(input_frame, text="导入 TXT", command=self._import_txt)
        self.txt_button.grid(row=1, column=1, padx=6, pady=(8, 0))
        self.excel_button = ttk.Button(input_frame, text="导入 Excel", command=self._import_excel)
        self.excel_button.grid(row=1, column=2, padx=6, pady=(8, 0))
        self.remove_button = ttk.Button(input_frame, text="移除选中", command=self._remove_selected)
        self.remove_button.grid(row=1, column=3, padx=6, pady=(8, 0))
        self.clear_button = ttk.Button(input_frame, text="清空", command=self._clear_inputs)
        self.clear_button.grid(row=1, column=4, padx=6, pady=(8, 0))
        ttk.Label(input_frame, text="使用日期").grid(row=1, column=5, padx=(20, 6), pady=(8, 0))
        ttk.Entry(input_frame, textvariable=self.date_var, width=12).grid(row=1, column=6, pady=(8, 0))

        self.input_tree = ttk.Treeview(input_frame, columns=("vendor", "url", "source"), show="headings", height=7)
        self.input_tree.heading("vendor", text="厂商")
        self.input_tree.heading("url", text="商品 URL")
        self.input_tree.heading("source", text="来源")
        self.input_tree.column("vendor", width=130, stretch=False)
        self.input_tree.column("url", width=650)
        self.input_tree.column("source", width=160, stretch=False)
        self.input_tree.grid(row=2, column=0, columnspan=7, sticky="nsew", pady=(8, 0))

        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X, pady=10)
        ttk.Label(controls, text="输出目录").pack(side=tk.LEFT)
        ttk.Entry(controls, textvariable=self.output_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.output_button = ttk.Button(controls, text="选择", command=self._choose_output)
        self.output_button.pack(side=tk.LEFT)
        self.start_button = ttk.Button(controls, text="开始", command=self._start)
        self.start_button.pack(side=tk.LEFT, padx=(14, 4))
        self.pause_button = ttk.Button(controls, textvariable=self.pause_text, command=self._toggle_pause)
        self.pause_button.pack(side=tk.LEFT, padx=4)
        self.stop_button = ttk.Button(controls, text="停止", command=self._stop)
        self.stop_button.pack(side=tk.LEFT, padx=4)
        self.open_button = ttk.Button(controls, text="打开输出", command=self._open_output)
        self.open_button.pack(side=tk.LEFT, padx=(4, 0))

        body = ttk.Panedwindow(outer, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)
        result_frame = ttk.LabelFrame(body, text="商品结果", padding=8)
        log_frame = ttk.LabelFrame(body, text="运行日志", padding=8)
        body.add(result_frame, weight=2)
        body.add(log_frame, weight=3)

        self.result_tree = ttk.Treeview(result_frame, columns=("product", "available", "trusted", "failures"), show="headings")
        self.result_tree.heading("product", text="商品")
        self.result_tree.heading("available", text="可售 SKU")
        self.result_tree.heading("trusted", text="可信价格")
        self.result_tree.heading("failures", text="失败")
        self.result_tree.column("product", width=280)
        self.result_tree.column("available", width=80, anchor="center")
        self.result_tree.column("trusted", width=80, anchor="center")
        self.result_tree.column("failures", width=60, anchor="center")
        self.result_tree.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        status = ttk.Frame(outer)
        status.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(status, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(status, textvariable=self.progress_var, relief=tk.SUNKEN, width=12, anchor="center").pack(side=tk.RIGHT)

    def _config(self) -> RunConfig:
        try:
            usage_date = date.fromisoformat(self.date_var.get().strip())
            port = int(self.port_var.get().strip())
        except ValueError as exc:
            raise ValueError("日期必须是 YYYY-MM-DD，CDP 端口必须是整数") from exc
        output = Path(self.output_var.get()).expanduser()
        return RunConfig(
            usage_date=usage_date,
            output_dir=output,
            market=self.market_var.get(),
            cdp_url=f"http://127.0.0.1:{port}",
        )

    def _checkpoint_factory(self, config: RunConfig):
        return RunExporter(config).checkpoint

    def _connect(self) -> None:
        try:
            self.worker.connect(self._config())
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))

    def _add_manual(self) -> None:
        try:
            self.inputs.extend(load_manual_urls(self.manual_text.get("1.0", tk.END), len(self.inputs)))
            self.inputs = deduplicate_inputs(self.inputs)
            self.manual_text.delete("1.0", tk.END)
            self._refresh_inputs()
        except ValueError as exc:
            messagebox.showerror("URL 错误", str(exc))

    def _import_txt(self) -> None:
        filename = filedialog.askopenfilename(filetypes=[("文本文件", "*.txt"), ("全部文件", "*")])
        if not filename:
            return
        try:
            self.inputs.extend(load_txt(Path(filename), len(self.inputs)))
            self.inputs = deduplicate_inputs(self.inputs)
            self._refresh_inputs()
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc))

    def _import_excel(self) -> None:
        filename = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx")])
        if not filename:
            return
        try:
            items, warnings = load_vendor_excel(Path(filename), len(self.inputs))
            self.inputs.extend(items)
            self.inputs = deduplicate_inputs(self.inputs)
            self._refresh_inputs()
            for warning in warnings:
                self._log(warning)
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc))

    def _remove_selected(self) -> None:
        selected = {int(value) for value in self.input_tree.selection()}
        self.inputs = [item for index, item in enumerate(self.inputs) if index not in selected]
        self._refresh_inputs()

    def _clear_inputs(self) -> None:
        self.inputs.clear()
        self._refresh_inputs()

    def _refresh_inputs(self) -> None:
        self.input_tree.delete(*self.input_tree.get_children())
        for index, item in enumerate(self.inputs):
            source = str(item.source_path) if item.source_path else "手动"
            self.input_tree.insert("", tk.END, iid=str(index), values=(item.vendor, item.url, source))
        self._apply_policy()

    def _choose_output(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_var.get())
        if selected:
            self.output_var.set(selected)

    def _start(self) -> None:
        if not self.inputs:
            messagebox.showwarning("没有任务", "请先添加 KKday 商品 URL")
            return
        try:
            config = self._config()
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return
        self.result_tree.delete(*self.result_tree.get_children())
        self.last_result = None
        self.last_output = None
        self.worker.run(self.inputs, config)

    def _toggle_pause(self) -> None:
        if self.phase is RunPhase.RUNNING:
            self.worker.pause()
        elif self.phase is RunPhase.PAUSED:
            self.worker.resume()

    def _stop(self) -> None:
        self.worker.stop()

    def _poll_events(self) -> None:
        try:
            while True:
                self._handle_event(self.events.get_nowait())
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _handle_event(self, event: AppEvent) -> None:
        if event.phase is not None:
            self.phase = event.phase
        if event.message:
            self._log(event.message)
            self.status_var.set(event.message)
        if event.current is not None and event.total is not None:
            self.progress_var.set(f"{event.current} / {event.total}")
        if isinstance(event.payload, SessionProbe):
            self.session_var.set("可用" if event.payload.api_ready else "需要验证")
            self.currency_var.set(event.payload.currency or "—")
        elif event.kind is EventKind.PRODUCT_RESULT and isinstance(event.payload, ProductResult):
            product = event.payload
            name = product.snapshot.name if product.snapshot else product.input_item.url
            available = len([row for row in product.rows if row.available])
            trusted = len(product.trusted_rows)
            self.result_tree.insert("", tk.END, values=(name, available, trusted, len(product.failures)))
        elif event.kind is EventKind.FINISHED and isinstance(event.payload, RunResult):
            self.last_result = event.payload
            self.last_output = event.payload.output_path
            if self.last_output:
                self._log(f"输出：{self.last_output}")
        self.pause_text.set("继续" if self.phase is RunPhase.PAUSED else "暂停")
        self._apply_policy()

    def _log(self, message: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _apply_policy(self) -> None:
        policy = button_policy(self.phase, bool(self.inputs), self.last_result is not None)
        self.connect_button.configure(state=tk.NORMAL if policy.connect else tk.DISABLED)
        input_state = tk.NORMAL if policy.edit_inputs else tk.DISABLED
        for button in (self.add_button, self.txt_button, self.excel_button, self.remove_button, self.clear_button, self.output_button):
            button.configure(state=input_state)
        self.start_button.configure(state=tk.NORMAL if policy.start else tk.DISABLED)
        self.pause_button.configure(state=tk.NORMAL if policy.pause or policy.resume else tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL if policy.stop else tk.DISABLED)
        self.open_button.configure(state=tk.NORMAL if policy.export and self.last_output else tk.DISABLED)

    def _open_output(self) -> None:
        if self.last_output is None:
            return
        target = self.last_output.parent
        if platform.system() == "Windows":
            subprocess.Popen(["explorer", str(target)])
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])

    def _on_close(self) -> None:
        if self.phase in {RunPhase.RUNNING, RunPhase.PAUSED} and not messagebox.askyesno("退出", "任务仍在运行。停止任务并退出吗？"):
            return
        self.worker.shutdown()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    KKdayScraperApp(root)
    root.mainloop()
```

- [ ] **Step 6: Replace the legacy single-file application with the compatibility launcher**

Replace all content of `kkday_get_scoreandprice.pyw` with:

```python
from kkday_scraper.gui import main


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Run offline tests and import smoke**

Run:

```bash
python3 -m pytest -q
python3 -m compileall -q kkday_scraper kkday_get_scoreandprice.pyw
python3 -c "from kkday_scraper.gui import KKdayScraperApp; print(KKdayScraperApp.__name__)"
```

Expected: all tests pass, compileall exits 0, and the import smoke prints `KKdayScraperApp`.

- [ ] **Step 8: Verify the legacy scraping path is gone**

Run:

```bash
rg -n "undetected_chromedriver|selenium|KKdayAntiDetectionHelper|_dfs_traverse_kkday|navigator\.webdriver|window\.chrome" . -g '*.py' -g '*.pyw'
```

Expected: no matches.

- [ ] **Step 9: Commit the GUI replacement**

```bash
git add kkday_scraper/gui.py kkday_scraper/gui_state.py tests/test_gui_state.py kkday_get_scoreandprice.pyw
git commit -m "feat: rebuild KKday scraper desktop workflow"
```

---

### Task 10: Add Live Contract Verification and Operator Documentation

**Files:**
- Create: `tests/test_live_kkday_contract.py`
- Create: `README.md`
- Create: `docs/architecture.md`

**Interfaces:**
- Consumes: the full package built in Tasks 1–9.
- Produces: an opt-in live test that proves every available SKU has a price and every package minimum matches the independent calendar endpoint.
- Produces: deterministic install, browser authorization, GUI run, input, output, recovery, and troubleshooting instructions.
- Guarantees: live test reads public product data only and never writes session secrets.

- [ ] **Step 1: Write the opt-in live contract test**

Create `tests/test_live_kkday_contract.py`:

```python
import os
from datetime import date, timedelta
from pathlib import Path

import pytest

from kkday_scraper.browser_api import BrowserApiClient
from kkday_scraper.browser_session import BrowserSession
from kkday_scraper.models import InputItem, RunConfig
from kkday_scraper.product_scraper import extract_product_snapshot
from kkday_scraper.sku_parser import package_minimum, parse_item_payload, validate_package_minimum


pytestmark = pytest.mark.live


def test_live_browser_context_returns_complete_sku_prices(tmp_path: Path) -> None:
    url = os.environ.get("KKDAY_LIVE_URL")
    cdp_url = os.environ.get("KKDAY_CDP_URL")
    if not url or not cdp_url:
        pytest.skip("set KKDAY_LIVE_URL and KKDAY_CDP_URL to run live contract test")

    usage_date = date.fromisoformat(os.environ.get("KKDAY_USAGE_DATE", date.today().isoformat()))
    config = RunConfig(usage_date=usage_date, output_dir=tmp_path, cdp_url=cdp_url)
    session = BrowserSession(config)
    try:
        session.connect(allow_launch=False)
        session.page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        session.page.wait_for_function(
            "() => Boolean(window.__NUXT__?.pinia?.['option-section']?.packages)",
            timeout=45_000,
        )
        probe = session.probe(config.market)
        assert probe.api_ready, probe.block_reason
        snapshot = extract_product_snapshot(session.page, url)
        api = BrowserApiClient(session.page, config.market, config.request_timeout_ms)
        end_date = usage_date + timedelta(days=40)
        calendar = api.fetch_package_calendar(snapshot.product_id, usage_date, end_date)

        total_available = 0
        for package in snapshot.packages:
            payload = api.fetch_items_data(package.package_id, package.item_ids, usage_date, end_date)
            package_rows = []
            for item_id in package.item_ids:
                package_rows.extend(
                    parse_item_payload(
                        payload=payload,
                        input_item=InputItem(url),
                        product_id=snapshot.product_id,
                        product_name=snapshot.name,
                        package=package,
                        item_id=item_id,
                        usage_date=usage_date,
                        currency=probe.currency,
                    )
                )
            available = [row for row in package_rows if row.available]
            total_available += len(available)
            assert available
            assert all(row.sale_price is not None for row in available)
            assert validate_package_minimum(
                package_rows,
                package_minimum(calendar, package.package_id, usage_date),
            ) == (True, "")

        assert total_available > 0
    finally:
        session.close()
```

- [ ] **Step 2: Write the concise operator README**

Create `README.md` with this exact structure and commands:

````markdown
# KKday SKU 价格抓取工具

Python 桌面程序通过真实 Chrome/Edge CDP 会话访问 KKday，在浏览器页面内调用只读商品接口，并导出指定日期的可售 SKU 与价格。

## 安装

```bash
cd /Users/tashima_meru/Develop/kkday_get_scoreandprice
python3 -m pip install -e '.[dev]'
```

## 浏览器准备

优先使用已经打开并通过 KKday 验证的 Chrome/Edge。浏览器需要开放 CDP 端口，默认 `9222`。程序连接失败时会启动专用可见 Chrome 配置；遇到 DataDome 验证时由用户在该浏览器中完成验证，再点击「连接 / 重新检测」。

程序不会把 Cookie、CSRF、密码或验证码写入项目或导出文件。

## 启动

```bash
python3 kkday_get_scoreandprice.pyw
```

运行顺序：

1. 点击「连接 / 重新检测」，确认状态为「可用」并检查币种。
2. 输入一个或多个 KKday 商品 URL，或导入 TXT/Excel。
3. 设置明确的使用日期和输出目录。
4. 点击「开始」。
5. 完成后点击「打开输出」。

Excel 批量输入格式：第一行为厂商名，第 2 行起为对应 KKday 商品 URL。

## 输出

默认目录：`~/Downloads/KKday_scraping/<运行时间>/`

- `kkday_price_results.xlsx`
- `run_summary.json`
- `failures.jsonl`（仅有失败时生成）

工作簿包含 `可售SKU`、`失败与警告`、`运行摘要` 三个工作表。价格行同时保留当前价格、原价、币种、使用日期、价格来源和质量状态。

## 停止与恢复

- 暂停在当前接口请求完成后生效。
- 停止会保留已经完成商品的部分工作簿。
- 401、403 或 HTML challenge 会停止整个批次。先在浏览器完成验证，再点击「连接 / 重新检测」并重新开始剩余 URL。
- `schema_unknown`、`missing_price`、`minimum_mismatch` 不会被当作可信价格。

## 测试

```bash
python3 -m pytest -q
python3 -m compileall -q kkday_scraper kkday_get_scoreandprice.pyw
```

授权浏览器的可选实时契约测试：

```bash
KKDAY_CDP_URL=http://127.0.0.1:9222 \
KKDAY_LIVE_URL='https://www.kkday.com/zh-tw/product/149025-japan-network-card-softbank-high-speed-500mb-1gb-2gb-3gb-esim' \
KKDAY_USAGE_DATE=2026-07-22 \
python3 -m pytest tests/test_live_kkday_contract.py -m live -q
```
````

- [ ] **Step 3: Document the architecture and failure policy**

Create `docs/architecture.md`:

````markdown
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

The program creates a tool-owned page inside the existing CDP browser context. This page inherits browser cookies and fingerprint, but Python never reads or persists those values. Direct HTTP is excluded from the production path because the verified endpoints returned 403 without browser credentials and still returned 403 when only browser-like header values were copied.

## Failure stop rules

- `401`, `403`, HTML response, or DataDome challenge: stop the batch and require an explicit browser probe.
- Network/5xx/read timeout: retry twice with 1-second and 3-second waits, then record a retryable API failure.
- Missing Nuxt fields or non-empty unrecognized `skusPriceCalendar`: record non-trusted schema failure; do not click every SKU or invent a response shape.
- Available SKU without `single_price.fullday`: record missing price.
- SKU minimum different from package calendar: record minimum mismatch.
- User stop: finish the in-flight read, atomically save completed products, and exit the batch.

## Security boundary

Allowed durable data: product URL/ID, package/item/SKU IDs, specification names, availability, price, currency, endpoint path shape, status classification, and timestamps.

Forbidden durable data: Cookie values, Authorization values, CSRF values, passwords, OTP/verification codes, member UUIDs, login IDs, email, phone, passport data, and raw member-status responses.
````

- [ ] **Step 4: Run the complete offline verification stack**

Run:

```bash
python3 -m pytest -q -m 'not live'
python3 -m compileall -q kkday_scraper kkday_get_scoreandprice.pyw
rg -n "Cookie|Authorization|csrf_hash|memberUuid|loginId|password" kkday_scraper tests README.md docs/architecture.md
```

Expected:

- all offline tests pass;
- compileall exits 0;
- the secret scan finds only explanatory forbidden-field documentation or explicit redaction tests, never captured values.

- [ ] **Step 5: Run the verified product live contract once**

With the real browser already authorized on port 9222, run:

```bash
KKDAY_CDP_URL=http://127.0.0.1:9222 \
KKDAY_LIVE_URL='https://www.kkday.com/zh-tw/product/149025-japan-network-card-softbank-high-speed-500mb-1gb-2gb-3gb-esim' \
KKDAY_USAGE_DATE=2026-07-22 \
python3 -m pytest tests/test_live_kkday_contract.py -m live -q
```

Expected: `1 passed`; every available SKU has a sale price and both package minimum checks pass. If KKday prices or availability have changed, counts may differ from the exploration result of 57 and 16, but completeness and minimum invariants must still pass.

- [ ] **Step 6: Perform manual GUI acceptance**

Run:

```bash
python3 kkday_get_scoreandprice.pyw
```

Verify this exact sequence:

1. The initial GUI shows disabled Start/Pause/Stop and enabled URL import controls.
2. Connecting displays safe session status, currency, and no raw credential values.
3. Adding the verified URL enables Start only after the browser phase is `ready`.
4. Starting processes two packages without cycling through every `.spec-btn`.
5. Pausing between packages changes the button to Continue and does not freeze Tk.
6. Stopping after a completed product leaves a readable partial workbook.
7. A successful run writes the three workbook sheets and opens the run directory.
8. The row for `無限流量（保證不降速） | 1 日` matches the browser-visible price for the same currency and usage date when manually selected.

- [ ] **Step 7: Commit live verification and documentation**

```bash
git add tests/test_live_kkday_contract.py README.md docs/architecture.md
git commit -m "docs: document KKday browser API scraping workflow"
```

---

## Final Verification Gate

Run from `/Users/tashima_meru/Develop/kkday_get_scoreandprice`:

```bash
git status --short
python3 -m pytest -q -m 'not live'
python3 -m compileall -q kkday_scraper kkday_get_scoreandprice.pyw
rg -n "undetected_chromedriver|selenium|KKdayAntiDetectionHelper|_dfs_traverse_kkday|navigator\.webdriver|window\.chrome" . -g '*.py' -g '*.pyw'
```

Expected:

- the worktree contains only intentional plan/implementation changes;
- all offline tests pass;
- compileall exits 0;
- no obsolete Selenium/stealth/DOM-DFS handle remains.

Then run the opt-in live test and manual GUI sequence from Task 10. Do not call the rebuild complete if only offline tests pass: live interface verification and visible GUI acceptance are separate required evidence.

## Self-Review Results

### Spec coverage

- GUI reconstruction: Task 9.
- Program/task logic reconstruction: Tasks 1, 2, 6, 7, and 8.
- Price acquisition reconstruction: Tasks 3, 4, 5, and 6.
- Real browser login/DataDome context without persisted secrets: Tasks 4 and 5.
- Single URL, multi-URL, TXT, and Excel input: Tasks 2 and 9.
- Finite retries, pause, stop, blocked-session handling, and partial output: Tasks 6–8.
- Removal of obsolete invasive stealth and click-DFS path: Task 9 plus Final Verification Gate.
- Offline, live, and rendered/manual acceptance: Tasks 1–10 and Final Verification Gate.

### Type consistency

- `RunConfig`, `InputItem`, `SessionProbe`, `PackageRef`, `SkuRow`, `ProductResult`, `RunResult`, and `AppEvent` are defined once in Task 1 and used with the same names in every later task.
- `BrowserSession.page` is the single page passed to `BrowserApiClient` and `ProductScraper`.
- `RunExporter.checkpoint(products, final)` matches the `Checkpoint` callable consumed by `TaskRunner` and `WorkerService`.
- `WorkerService` is the only cross-thread browser owner; GUI receives only `AppEvent` values.

### Scope discipline

- No multi-worker scheduler, cron integration, vendor comparison workbook, hidden headless mode, cookie store, proxy rotation, CAPTCHA solver, account login automation, or speculative dynamic-price parser is included.
- A future non-empty `skusPriceCalendar` must first be captured and fixture-tested in a separate change; this plan deliberately fails closed instead of inferring an unverified schema.
# Historical plan notice

This document describes the earlier scraper rebuild and is retained for
history. Its attach/fallback browser section is superseded by the current
runtime in `kkday_scraper/browser_bootstrap.py`: use the explicit existing-CDP
or dedicated-profile bootstrap paths documented in `README.md` and
`docs/architecture.md`. Do not copy its older fallback snippets into runtime
code.
