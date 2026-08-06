from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from .cookie_store import ALLOWED_COOKIE_NAMES, load_preference_cookies
from .models import RunConfig, SessionProbe, market_homepage


RESULT_MARKER = "__KKDAY_EGO_RESULT__"
Runner = Callable[[list[str], str, float], tuple[int, str, str]]


class EgoBrowserError(RuntimeError):
    """A safe, user-facing ego-browser runtime or ownership failure."""


def _default_runner(
    command: list[str], script: str, timeout: float
) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            command,
            input=script,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise EgoBrowserError(
            "ego-browser 不可用；请确认 ego lite 已安装并在当前图形登录会话中运行"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise EgoBrowserError("ego-browser 操作超时") from exc
    return completed.returncode, completed.stdout, completed.stderr


def _safe_error(text: str) -> str:
    value = text.strip() or "ego-browser 返回未知错误"
    value = re.sub(r"(?i)(cookie|authorization|password|token)\s*[:=]\s*\S+", r"\1=<redacted>", value)
    value = re.sub(r"wss?://\S+", "<browser-connection-redacted>", value)
    return value[-1200:]


def _is_ownership_stop(message: str) -> bool:
    lowered = message.lower()
    return any(
        marker in lowered
        for marker in (
            "user is controlling",
            "inactive task space",
            "not assigned to an agent",
            "user-owned",
        )
    )


def default_task_space(market: str) -> str:
    return f"kkday-sku-price-{market}"


def build_agent_handoff(
    *,
    task_space_id: int | str | None,
    task_space_name: str,
    reason: str,
    product_url: str | None = None,
) -> dict[str, object]:
    prompt = (
        f"KKday 抓取在同一个 task space（名称 {task_space_name}，ID {task_space_id}）中"
        f"遇到挑战：{reason}。请复用这个 task space，不要创建替代空间；使用 ego-browser 或 "
        "Computer Use 查看可见页面，只尝试等待、刷新一次、确认语言/地区、关闭普通提示框，"
        "或在账号密码已由浏览器自动填充时点击一次登录。不得读取、导出或修改凭据，不得规避 "
        "CAPTCHA、指纹或安全机制。若出现 CAPTCHA、MFA、账号选择或安全确认，请通过 "
        "ego-browser handOffTaskSpace 移交真人；真人明确完成后再接管原 task space，重新探测，"
        "并以完全相同参数重跑一次。恢复重试上限为 1 次。"
    )
    return {
        "type": "handoff_required",
        "message": "KKday 页面需要 Agent 或人工完成可见验证",
        "reason": reason,
        "task_space_id": task_space_id,
        "task_space_name": task_space_name,
        "product_url": product_url,
        "agent_prompt": prompt,
        "retry_limit": 1,
    }


def classify_probe(raw: dict[str, Any], page_url: str, market: str) -> SessionProbe:
    status = int(raw.get("status") or 0)
    content_type = str(raw.get("contentType") or "").lower()
    contract_ok = bool(raw.get("contractOk"))
    blocked = status in {401, 403} or "text/html" in content_type
    if blocked:
        reason = "KKday 返回 403/HTML，ego-browser task space 需要可见验证"
    elif status != 200 or "json" not in content_type or not contract_ok:
        reason = "KKday 会话检测接口返回异常"
    else:
        reason = None
    return SessionProbe(
        connected=True,
        member_api_ready=status == 200 and "json" in content_type and contract_ok,
        is_login=bool(raw.get("isLogin")),
        currency=str(raw.get("currency") or ""),
        market=market,
        page_url=page_url,
        block_reason=reason,
    )


PROBE_SCRIPT = """
async ({ market }) => {
  const response = await fetch(`/api/_nuxt/member/get-member-status?t=${Date.now()}`, {
    method: "GET", credentials: "include", headers: { market }
  });
  const contentType = response.headers.get("content-type") || "";
  let data = null;
  if (contentType.includes("application/json")) data = await response.json();
  return {
    status: response.status, contentType,
    contractOk: Boolean(data && data.data && (data.message === "success" || data.result === "BASE_SUCCESS")),
    isLogin: Boolean(data && data.data && data.data.isLogin),
    currency: data && data.data && data.data.currency ? String(data.data.currency) : ""
  };
}
"""


class EgoPage:
    def __init__(self, bridge: "EgoBrowserBridge") -> None:
        self.bridge = bridge
        self._url = ""

    @property
    def url(self) -> str:
        return self._url

    def goto(self, url: str, **kwargs: object) -> None:
        timeout_ms = int(kwargs.get("timeout") or self.bridge.config.request_timeout_ms)
        result = self.bridge._task_call(
            f"""
const tab = await ensureRealTab()
if (tab) {{ await gotoAndWait({json.dumps(url)}, {{ timeout: {max(1, timeout_ms // 1000)}, settle: 1 }}) }}
else {{ await openOrReuseTab({json.dumps(url)}, {{ wait: true, timeout: {max(1, timeout_ms // 1000)} }}) }}
const info = await pageInfo()
cliLog({json.dumps(RESULT_MARKER)} + JSON.stringify({{ url: info.url || {json.dumps(url)} }}))
""",
            timeout=max(30.0, timeout_ms / 1000 + 15),
        )
        self._url = str(result.get("url") or url)

    def evaluate(self, expression: str, arg: object = None) -> object:
        source = json.dumps(expression)
        argument = json.dumps(arg, ensure_ascii=False, default=str)
        result = self.bridge._task_call(
            f"""
await ensureRealTab()
const source = {source}
const argument = {argument}
const value = await js('(' + source + ')(' + JSON.stringify(argument) + ')')
const info = await pageInfo()
cliLog({json.dumps(RESULT_MARKER)} + JSON.stringify({{ value, url: info.url || '' }}))
"""
        )
        self._url = str(result.get("url") or self._url)
        return result.get("value")

    def wait_for_function(self, expression: str, **kwargs: object) -> None:
        timeout_ms = int(kwargs.get("timeout") or self.bridge.config.request_timeout_ms)
        source = json.dumps(expression)
        self.bridge._task_call(
            f"""
await ensureRealTab()
const source = {source}
const timeoutMs = {timeout_ms}
const value = await js(`(async () => {{
  const deadline = Date.now() + ${{{timeout_ms}}};
  while (Date.now() < deadline) {{
    if (await (${{source}})()) return true;
    await new Promise(resolve => setTimeout(resolve, 200));
  }}
  throw new Error('wait_for_function timeout');
}})()`)
cliLog({json.dumps(RESULT_MARKER)} + JSON.stringify({{ value }}))
""",
            timeout=max(30.0, timeout_ms / 1000 + 15),
        )


class EgoBrowserBridge:
    def __init__(self, config: RunConfig, runner: Runner | None = None) -> None:
        self.config = config
        self.task_space_name = config.ego_task_space or default_task_space(config.market)
        self.task_space_id: int | str | None = None
        self.page = EgoPage(self)
        self._runner = runner or _default_runner
        self._connected = False
        self._preserve = False
        self._closed = False

    def _invoke(self, script: str, timeout: float = 75.0) -> dict[str, Any]:
        code, stdout, stderr = self._runner(["ego-browser", "nodejs"], script, timeout)
        if code != 0:
            message = _safe_error(stderr or stdout)
            if _is_ownership_stop(message):
                self._preserve = True
            raise EgoBrowserError(message)
        output = "\n".join((stdout, stderr))
        marker_lines = [
            line for line in output.splitlines() if line.startswith(RESULT_MARKER)
        ]
        if not marker_lines:
            raise EgoBrowserError("ego-browser 未返回可验证的结构化结果")
        try:
            payload = json.loads(marker_lines[-1][len(RESULT_MARKER):])
        except json.JSONDecodeError as exc:
            raise EgoBrowserError("ego-browser 返回结构无法解析") from exc
        if not isinstance(payload, dict):
            raise EgoBrowserError("ego-browser 返回了未知结构")
        return payload

    def _task_call(self, body: str, timeout: float = 75.0) -> dict[str, Any]:
        selector: object = self.task_space_id if self.task_space_id is not None else self.task_space_name
        return self._invoke(
            f"const task = await useOrCreateTaskSpace({json.dumps(selector)})\n{body}",
            timeout,
        )

    def connect(self) -> None:
        if self._connected:
            return
        homepage = market_homepage(self.config.market)
        cookies = [c for c in load_preference_cookies() if c.get("name") in ALLOWED_COOKIE_NAMES]
        cookie_script = ""
        for cookie in cookies:
            params = {
                "name": cookie["name"], "value": cookie["value"],
                "domain": cookie["domain"], "path": cookie["path"],
                "secure": True, "httpOnly": bool(cookie.get("httpOnly", True)),
            }
            cookie_script += f"await cdp('Network.setCookie', {json.dumps(params, ensure_ascii=False)})\n"
        result = self._task_call(
            f"""
await openOrReuseTab({json.dumps(homepage)}, {{ wait: true, timeout: 60 }})
{cookie_script}const info = await pageInfo()
cliLog({json.dumps(RESULT_MARKER)} + JSON.stringify({{
  taskSpaceId: task.id, taskSpaceName: task.name || {json.dumps(self.task_space_name)}, url: info.url || ''
}}))
""",
            timeout=90.0,
        )
        self.task_space_id = result.get("taskSpaceId")
        self.task_space_name = str(result.get("taskSpaceName") or self.task_space_name)
        self.page._url = str(result.get("url") or homepage)
        self._connected = True

    def probe_member(self, market: str) -> SessionProbe:
        self.page.goto(market_homepage(market), timeout=60_000)
        raw = self.page.evaluate(PROBE_SCRIPT, {"market": market})
        if not isinstance(raw, dict):
            raise EgoBrowserError("ego-browser 会话检测返回了未知结构")
        return classify_probe(raw, self.page.url, market)

    def preserve_for_handoff(self) -> None:
        self._preserve = True

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if not self._connected or self._preserve:
            return
        selector: object = self.task_space_id if self.task_space_id is not None else self.task_space_name
        result = self._invoke(
            f"const result = await completeTaskSpace({json.dumps(selector)}, {{ keep: false }})\n"
            f"cliLog({json.dumps(RESULT_MARKER)} + JSON.stringify(result))\n"
        )
        if result.get("done") is not True:
            raise EgoBrowserError("ego-browser task space 清理未完成")


BrowserSession = EgoBrowserBridge
