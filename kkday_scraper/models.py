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
    AUTH_REQUIRED = "auth_required"
    READY = "ready"
    VERIFYING = "verifying"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
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
    NO_PACKAGES = "no_packages"
    SESSION_BLOCKED = "session_blocked"
    SESSION_EXPIRED = "session_expired"
    NAVIGATION = "navigation"
    API = "api"
    SCHEMA = "schema"
    MISSING_PRICE = "missing_price"
    PRICE_MISMATCH = "price_mismatch"
    CURRENCY_MISMATCH = "currency_mismatch"
    STOPPED = "stopped"


class EventKind(str, Enum):
    PHASE = "phase"
    READINESS = "readiness"
    LOG = "log"
    PROGRESS = "progress"
    PRODUCT_RESULT = "product_result"
    FAILURE = "failure"
    FINISHED = "finished"
    HANDOFF_REQUIRED = "handoff_required"


@dataclass(frozen=True)
class EgoTaskSpaceInfo:
    task_space_id: int | str | None
    task_space_name: str


@dataclass(frozen=True)
class InputItem:
    url: str
    vendor: str = "手动输入"
    input_order: int = 0
    source_path: Path | None = None
    source_row: int | None = None
    source_column: int | None = None
    market: str | None = None


SUPPORTED_MARKETS = ("zh-tw", "zh-hk")


def market_homepage(market: str) -> str:
    if market not in SUPPORTED_MARKETS:
        raise ValueError(f"不支持的 KKday 站点：{market}")
    return f"https://www.kkday.com/{market}"


@dataclass(frozen=True)
class RunConfig:
    usage_date: date
    output_dir: Path
    market: str = "zh-tw"
    ego_task_space: str | None = None
    requested_count: int | None = None
    currency: str = "TWD"
    request_timeout_ms: int = 30_000
    request_retry_delays: tuple[float, ...] = (1.0, 3.0)
    product_delay_range: tuple[float, float] = (2.0, 4.0)
    package_delay_range: tuple[float, float] = (0.4, 0.9)
    include_unavailable: bool = False


@dataclass(frozen=True)
class SessionProbe:
    connected: bool
    member_api_ready: bool
    is_login: bool
    currency: str
    market: str
    page_url: str
    block_reason: str | None = None


@dataclass(frozen=True)
class ReadinessReport:
    browser_connected: bool
    member_api_ready: bool | None
    product_page_ready: bool | None
    price_calendar_ready: bool | None
    sku_api_ready: bool | None
    product_url: str | None
    currency: str = ""
    reason: str | None = None
    is_login: bool | None = None

    @classmethod
    def from_member_probe(cls, probe: SessionProbe) -> ReadinessReport:
        return cls(
            browser_connected=probe.connected,
            member_api_ready=probe.member_api_ready,
            product_page_ready=None,
            price_calendar_ready=None,
            sku_api_ready=None,
            product_url=None,
            currency=probe.currency,
            reason=probe.block_reason,
            is_login=probe.is_login,
        )

    @property
    def business_ready(self) -> bool:
        return (
            self.browser_connected
            and self.member_api_ready is True
            and self.product_page_ready is True
            and self.price_calendar_ready is True
            and self.sku_api_ready is True
        )


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
    destination: str = ""
    rating: float | None = None
    review_count: int | None = None
    sold_count: int | None = None
    wishlist_count: int | None = None
    page_min_price: Decimal | None = None
    confirmation: str = ""
    cancellation_policy: str = ""
    features: tuple[str, ...] = ()


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
    market: str = ""
    captured_at: datetime = field(default_factory=datetime.now)
    tree_order: tuple[int, ...] = ()

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
        return tuple(
            row for row in self.rows if row.price_status is PriceStatus.TRUSTED
        )


@dataclass(frozen=True)
class RunResult:
    products: tuple[ProductResult, ...]
    output_path: Path | None
    started_at: datetime
    finished_at: datetime
    stopped: bool = False
    terminal_phase: RunPhase = RunPhase.COMPLETED
    requested_count: int = 0
    processed_count: int = 0
    final_checkpoint_saved: bool = False

    @property
    def rows(self) -> tuple[SkuRow, ...]:
        return tuple(row for product in self.products for row in product.rows)

    @property
    def failures(self) -> tuple[FailureRecord, ...]:
        return tuple(
            failure for product in self.products for failure in product.failures
        )


@dataclass(frozen=True)
class AppEvent:
    kind: EventKind
    message: str = ""
    phase: RunPhase | None = None
    current: int | None = None
    total: int | None = None
    payload: Any = None
