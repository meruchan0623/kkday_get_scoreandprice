from kkday_scraper.gui_state import (
    button_policy,
    readiness_labels,
    session_allows_product_preflight,
)
from kkday_scraper.models import ReadinessReport, RunPhase


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


def test_connecting_and_stopping_disable_export() -> None:
    connecting = button_policy(RunPhase.CONNECTING, True, True)
    assert connecting.export is False
    assert connecting.stop is False
    assert button_policy(RunPhase.STOPPING, True, True).export is False


def test_verifying_disables_edits_and_pause_but_allows_stop() -> None:
    policy = button_policy(RunPhase.VERIFYING, True, False)

    assert policy.connect is False
    assert policy.edit_inputs is False
    assert policy.start is False
    assert policy.pause is False
    assert policy.stop is True


def test_auth_required_allows_reconnect_and_manual_login_probe() -> None:
    policy = button_policy(RunPhase.AUTH_REQUIRED, True, False)

    assert policy.connect is True
    assert policy.probe is True
    assert policy.start is False


def test_member_ready_labels_product_and_sku_as_pending() -> None:
    labels = readiness_labels(
        ReadinessReport(
            browser_connected=True,
            member_api_ready=True,
            product_page_ready=None,
            price_calendar_ready=None,
            sku_api_ready=None,
            product_url=None,
            currency="KRW",
        )
    )

    assert labels.browser == "已连接"
    assert labels.member == "可用"
    assert labels.product == "待商品验证"
    assert labels.sku == "待商品验证"


def test_member_api_ready_without_login_allows_public_product_preflight() -> None:
    labels = readiness_labels(
        ReadinessReport(
            browser_connected=True,
            member_api_ready=True,
            product_page_ready=None,
            price_calendar_ready=None,
            sku_api_ready=None,
            product_url=None,
            currency="KRW",
            is_login=False,
        )
    )

    assert labels.member == "未登录（可验证公开商品）"
    assert session_allows_product_preflight(
        ReadinessReport(
            browser_connected=True,
            member_api_ready=True,
            product_page_ready=None,
            price_calendar_ready=None,
            sku_api_ready=None,
            product_url=None,
            is_login=False,
        )
    ) is True
    assert button_policy(
        RunPhase.READY,
        has_inputs=True,
        has_results=False,
        session_ready=True,
    ).start is True


def test_blocked_product_with_calendar_is_not_sku_ready() -> None:
    labels = readiness_labels(
        ReadinessReport(
            browser_connected=True,
            member_api_ready=True,
            product_page_ready=False,
            price_calendar_ready=True,
            sku_api_ready=None,
            product_url="https://www.kkday.com/zh-tw/product/149025-example",
            currency="KRW",
            reason="商品页被拦截，价格日历可用，但无法取得 SKU 树",
        )
    )

    assert labels.product == "被拦截"
    assert labels.sku == "价格日历可用，SKU 待恢复"


def test_normal_page_schema_failure_is_not_labeled_as_blocked() -> None:
    labels = readiness_labels(
        ReadinessReport(
            browser_connected=True,
            member_api_ready=True,
            product_page_ready=False,
            price_calendar_ready=None,
            sku_api_ready=None,
            product_url="https://www.kkday.com/zh-tw/product/149025-example",
            currency="KRW",
            reason="商品页结构异常：Nuxt option-section 缺少套餐结构",
        )
    )

    assert labels.product == "结构异常"


def test_blocked_state_allows_reconnect_and_probe_but_not_start() -> None:
    policy = button_policy(RunPhase.BLOCKED, has_inputs=True, has_results=False)

    assert policy.connect is True
    assert policy.probe is True
    assert policy.edit_inputs is True
    assert policy.start is False


def test_stopped_state_allows_a_clean_restart_and_previous_export() -> None:
    policy = button_policy(RunPhase.STOPPED, has_inputs=True, has_results=True)

    assert policy.connect is True
    assert policy.edit_inputs is True
    assert policy.start is True
    assert policy.export is True


def test_stopped_state_without_live_session_cannot_start() -> None:
    policy = button_policy(
        RunPhase.STOPPED,
        has_inputs=True,
        has_results=True,
        session_ready=False,
    )

    assert policy.start is False
