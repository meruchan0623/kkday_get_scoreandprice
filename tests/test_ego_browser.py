import json
from datetime import date
from pathlib import Path

import pytest

from kkday_scraper.ego_browser import (
    EgoBrowserBridge,
    EgoBrowserError,
    build_agent_handoff,
)
from kkday_scraper.models import RunConfig


MARKER = "__KKDAY_EGO_RESULT__"


class FakeRunner:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, command, script, timeout):
        self.calls.append((command, script, timeout))
        payload = self.results.pop(0)
        return 0, f"ego log\n{MARKER}{json.dumps(payload)}\n", ""


def test_bridge_reuses_named_task_space_and_evaluates_page_script(tmp_path: Path) -> None:
    runner = FakeRunner(
        [
            {"taskSpaceId": 71, "taskSpaceName": "kkday-sku-price-zh-tw", "url": "https://www.kkday.com/zh-tw"},
            {"value": {"status": 200}, "url": "https://www.kkday.com/zh-tw"},
        ]
    )
    bridge = EgoBrowserBridge(
        RunConfig(date(2026, 8, 6), tmp_path, ego_task_space="kkday-sku-price-zh-tw"),
        runner=runner,
    )

    bridge.connect()
    value = bridge.page.evaluate("async ({ market }) => ({ status: 200, market })", {"market": "zh-tw"})

    assert value == {"status": 200}
    assert bridge.task_space_id == 71
    assert all("useOrCreateTaskSpace" in call[1] for call in runner.calls)
    assert "takeOverTaskSpace" not in "\n".join(call[1] for call in runner.calls)
    assert "Storage.getCookies" not in "\n".join(call[1] for call in runner.calls)


def test_bridge_accepts_ego_cli_marker_from_stderr(tmp_path: Path) -> None:
    def runner(_command, _script, _timeout):
        payload = {"taskSpaceId": 70, "taskSpaceName": "stderr-space", "url": "https://www.kkday.com/zh-tw"}
        return 0, "", MARKER + json.dumps(payload) + "\n"

    bridge = EgoBrowserBridge(
        RunConfig(date(2026, 8, 6), tmp_path, ego_task_space="stderr-space"),
        runner=runner,
    )
    bridge.connect()
    assert bridge.task_space_id == 70


def test_bridge_uses_dedicated_completion_and_preserves_blocked_space(tmp_path: Path) -> None:
    runner = FakeRunner(
        [
            {"taskSpaceId": 72, "taskSpaceName": "batch", "url": "https://www.kkday.com/zh-tw"},
            {"done": True},
        ]
    )
    bridge = EgoBrowserBridge(RunConfig(date(2026, 8, 6), tmp_path, ego_task_space="batch"), runner=runner)
    bridge.connect()
    bridge.close()
    assert "completeTaskSpace" in runner.calls[-1][1]
    assert "useOrCreateTaskSpace" not in runner.calls[-1][1]

    preserve_runner = FakeRunner([{"taskSpaceId": 73, "taskSpaceName": "blocked", "url": "https://www.kkday.com/zh-tw"}])
    blocked = EgoBrowserBridge(RunConfig(date(2026, 8, 6), tmp_path, ego_task_space="blocked"), runner=preserve_runner)
    blocked.connect()
    blocked.preserve_for_handoff()
    blocked.close()
    assert len(preserve_runner.calls) == 1


@pytest.mark.parametrize("message", ["user is controlling", "inactive task space", "not assigned to an agent"])
def test_ownership_errors_are_hard_stops_without_retry(tmp_path: Path, message: str) -> None:
    runner = FakeRunner([])
    runner.results = []

    def fail(command, script, timeout):
        runner.calls.append((command, script, timeout))
        return 1, "", message

    bridge = EgoBrowserBridge(RunConfig(date(2026, 8, 6), tmp_path), runner=fail)
    with pytest.raises(EgoBrowserError, match=message):
        bridge.connect()
    assert len(runner.calls) == 1


def test_user_takeover_after_connect_preserves_space_without_completion(tmp_path: Path) -> None:
    calls = []

    def runner(command, script, timeout):
        calls.append((command, script, timeout))
        if len(calls) == 1:
            payload = {"taskSpaceId": 74, "taskSpaceName": "taken", "url": "https://www.kkday.com/zh-tw"}
            return 0, MARKER + json.dumps(payload), ""
        return 1, "", "user is controlling"

    bridge = EgoBrowserBridge(
        RunConfig(date(2026, 8, 6), tmp_path, ego_task_space="taken"),
        runner=runner,
    )
    bridge.connect()
    with pytest.raises(EgoBrowserError, match="user is controlling"):
        bridge.page.evaluate("() => true")
    bridge.close()

    assert len(calls) == 2
    assert all("completeTaskSpace" not in script for _, script, _ in calls)


def test_agent_handoff_is_structured_and_contains_no_sensitive_page_data() -> None:
    event = build_agent_handoff(
        task_space_id=88,
        task_space_name="kkday-sku-price-zh-tw",
        reason="KKday 返回 403/HTML",
        product_url="https://www.kkday.com/zh-tw/product/121004-example",
    )

    assert event["type"] == "handoff_required"
    assert event["retry_limit"] == 1
    assert event["task_space_id"] == 88
    assert "Computer Use" in event["agent_prompt"]
    assert "同一个 task space" in event["agent_prompt"]
    serialized = json.dumps(event, ensure_ascii=False).lower()
    for forbidden in ("cookie=", "authorization:", "password=", "websocket"):
        assert forbidden not in serialized
