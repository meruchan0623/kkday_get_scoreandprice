import json
import subprocess
from datetime import date
from pathlib import Path

import pytest

from kkday_scraper.ego_browser import (
    EgoBrowserBridge,
    EgoBrowserError,
    build_agent_handoff,
    passive_package_graph_init_source,
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
    assert all("taskSpace(" in call[1] for call in runner.calls)
    assert all("useOrCreateTaskSpace" not in call[1] for call in runner.calls)
    assert "takeOverTaskSpace" not in "\n".join(call[1] for call in runner.calls)
    assert "Storage.getCookies" not in "\n".join(call[1] for call in runner.calls)


def test_evaluate_embeds_serialized_argument_in_one_string_expression(tmp_path: Path) -> None:
    runner = FakeRunner([{"value": {"status": 200}, "url": "https://www.kkday.com/zh-tw"}])
    bridge = EgoBrowserBridge(RunConfig(date(2026, 8, 6), tmp_path), runner=runner)

    bridge.page.evaluate("async ({ market }) => ({ status: 200, market })", {"market": "zh-tw"})

    script = runner.calls[0][1]
    source_line = next(line for line in script.splitlines() if line.startswith("const source = "))
    browser_expression = json.loads(source_line.removeprefix("const source = "))
    assert '({"market": "zh-tw"})' in browser_expression
    assert "page.evaluate((source) => (0, eval)(source), source)" in script
    completed = subprocess.run(
        ["node", "-e", "(async()=>{const source=process.argv[1]; const value=await ((source)=>(0,eval)(source))(source); process.stdout.write(JSON.stringify(value));})().catch(error=>{console.error(error);process.exit(1)})", browser_expression],
        text=True, capture_output=True, check=True,
    )
    assert json.loads(completed.stdout) == {"status": 200, "market": "zh-tw"}


def test_passive_graph_hook_is_navigation_atomic_and_rejects_unverified_shapes(tmp_path: Path) -> None:
    runner = FakeRunner([{"url": "https://www.kkday.com/zh-tw/product/135034", "passiveGraph": None, "passiveDiagnostics": {}}])
    bridge = EgoBrowserBridge(RunConfig(date(2026, 8, 6), tmp_path), runner=runner)

    bridge.page.arm_passive_package_graph("https://www.kkday.com/zh-tw/product/135034")
    bridge.page.goto("https://www.kkday.com/zh-tw/product/135034")

    script = runner.calls[0][1]
    assert "Page.addScriptToEvaluateOnNewDocument" in script
    assert "await page.goto" in script
    assert script.index("Page.addScriptToEvaluateOnNewDocument") < script.index("await page.goto")
    assert "await page.waitForTimeout(250)" in script
    assert "page.evaluate(() =>" in script
    assert "passiveGraph" in script
    source = passive_package_graph_init_source("https://www.kkday.com/zh-tw/product/135034")
    assert 'request.pathname === "/api/_nuxt/product/fetch-packages-data"' in source
    assert 'request.searchParams.get("prodMid") === productId' in source
    assert "Number.isSafeInteger(setting?.prod_mid)" in source
    assert "Number.isSafeInteger(pkg.pkg_oid)" in source
    assert "Number.isSafeInteger(item.item_oid)" in source
    assert 'this.responseType === "json" ? this.response : this.responseText' in source
    assert 'payload.message !== "success"' in source
    assert "cliLog" not in source


@pytest.mark.parametrize("response_type", ["json", "text"])
def test_passive_observer_executes_for_json_or_text_xhr(response_type: str) -> None:
    source = passive_package_graph_init_source("https://www.kkday.com/zh-tw/product/135034")
    payload = {"message": "success", "data": {"PRODUCT-SETTING": {"prod_mid": 135034}, "PACKAGE": {"2555718": {"pkg_oid": 2555718, "name": "One", "items": [2301495]}}, "ITEM": {"2301495": {"item_oid": 2301495}}}}
    harness = r"""
globalThis.window = globalThis;
globalThis.location = new URL('https://www.kkday.com/zh-tw/product/135034');
globalThis.fetch = async () => { throw new Error('not used'); };
class Xhr {
  constructor() { this.listeners = {}; this.status = 200; this.responseType = process.argv[3]; this.response = JSON.parse(process.argv[2]); }
  open() {}
  send() {}
  addEventListener(kind, callback) { this.listeners[kind] = callback; }
  emit(kind) { this.listeners[kind](); }
  get responseText() { if (this.responseType === 'json') throw new Error('responseText must not be read for JSON XHR'); return JSON.stringify(this.response); }
}
globalThis.XMLHttpRequest = Xhr;
eval(process.argv[1]);
const xhr = new XMLHttpRequest();
xhr.open('GET', '/api/_nuxt/product/fetch-packages-data?prodMid=135034');
xhr.send(); xhr.emit('loadend');
process.stdout.write(JSON.stringify(window.__kkdayPassivePackageGraph));
"""
    completed = subprocess.run(
        ["node", "-e", harness, source, json.dumps(payload), response_type],
        text=True, capture_output=True, check=True,
    )
    assert json.loads(completed.stdout)["packages"][0]["itemIds"] == ["2301495"]


def test_passive_graph_is_cached_from_navigation_result(tmp_path: Path) -> None:
    graph = {"productId": "135034", "packages": [{"packageId": "2555718", "itemIds": ["2301495"]}]}
    runner = FakeRunner([{"url": "https://www.kkday.com/zh-tw/product/135034", "passiveGraph": graph, "passiveDiagnostics": {"graph": True}}])
    bridge = EgoBrowserBridge(RunConfig(date(2026, 8, 6), tmp_path), runner=runner)
    bridge.page.arm_passive_package_graph("https://www.kkday.com/zh-tw/product/135034")
    bridge.page.goto("https://www.kkday.com/zh-tw/product/135034")

    assert bridge.page.read_passive_package_graph() == graph
    assert len(runner.calls) == 1


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
    assert "task.finish({ keep: [] })" in runner.calls[-1][1]
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
