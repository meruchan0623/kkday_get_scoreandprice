from dataclasses import dataclass

from .models import RunPhase


@dataclass(frozen=True)
class ButtonPolicy:
    connect: bool
    bootstrap: bool
    probe: bool
    edit_inputs: bool
    start: bool
    pause: bool
    resume: bool
    stop: bool
    export: bool


@dataclass(frozen=True)
class ReadinessLabels:
    browser: str
    member: str
    product: str
    sku: str


def readiness_labels(report) -> ReadinessLabels:
    browser = "已连接" if report.browser_connected else "未连接"
    member = (
        "待检测"
        if report.member_api_ready is None
        else "未登录（可验证公开商品）"
        if report.member_api_ready and report.is_login is False
        else "可用" if report.member_api_ready else "异常"
    )
    if report.product_page_ready is None:
        product = "待商品验证"
    elif report.product_page_ready:
        product = "可用"
    elif report.reason and "结构异常" in report.reason:
        product = "结构异常"
    else:
        product = "被拦截"
    if report.sku_api_ready is True:
        sku = "可用"
    elif report.sku_api_ready is False:
        sku = "被拦截"
    elif report.price_calendar_ready is True and report.product_page_ready is False:
        sku = "价格日历可用，SKU 待恢复"
    else:
        sku = "待商品验证"
    return ReadinessLabels(browser, member, product, sku)


def session_allows_product_preflight(report) -> bool:
    return report.browser_connected and report.member_api_ready is True


def button_policy(
    phase: RunPhase,
    has_inputs: bool,
    has_results: bool,
    session_ready: bool = True,
) -> ButtonPolicy:
    busy = phase in {
        RunPhase.BOOTSTRAPPING,
        RunPhase.CONNECTING,
        RunPhase.VERIFYING,
        RunPhase.RUNNING,
        RunPhase.PAUSED,
        RunPhase.STOPPING,
    }
    return ButtonPolicy(
        connect=phase
        in {
            RunPhase.IDLE,
            RunPhase.AUTH_REQUIRED,
            RunPhase.READY,
            RunPhase.STOPPED,
            RunPhase.BLOCKED,
            RunPhase.COMPLETED,
            RunPhase.FAILED,
        },
        bootstrap=phase
        in {
            RunPhase.IDLE,
            RunPhase.AUTH_REQUIRED,
            RunPhase.READY,
            RunPhase.STOPPED,
            RunPhase.BLOCKED,
            RunPhase.COMPLETED,
            RunPhase.FAILED,
        },
        probe=phase in {RunPhase.READY, RunPhase.AUTH_REQUIRED, RunPhase.BLOCKED},
        edit_inputs=not busy,
        start=phase in {RunPhase.READY, RunPhase.STOPPED}
        and has_inputs
        and session_ready,
        pause=phase is RunPhase.RUNNING,
        resume=phase is RunPhase.PAUSED,
        stop=phase
        in {
            RunPhase.BOOTSTRAPPING,
            RunPhase.VERIFYING,
            RunPhase.RUNNING,
            RunPhase.PAUSED,
        },
        export=has_results
        and phase
        not in {RunPhase.BOOTSTRAPPING, RunPhase.CONNECTING, RunPhase.STOPPING},
    )
