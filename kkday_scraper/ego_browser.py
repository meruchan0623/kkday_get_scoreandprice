from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from .models import RunConfig, SessionProbe, market_homepage


RESULT_MARKER = "__KKDAY_EGO_RESULT__"
Runner = Callable[[list[str], str, float], tuple[int, str, str]]


def passive_package_graph_init_source(product_url: str) -> str:
    """Return a new-document hook that retains only a verified package graph.

    The hook observes the browser's ordinary frontend request.  It neither
    initiates a request nor exports a response body: reduced IDs and names live
    only in the current page's JavaScript heap.
    """
    target = json.dumps(product_url)
    return f"""
(() => {{
  const target = new URL({target});
  const productId = target.pathname.match(/\\/product\\/(\\d+)/)?.[1] || "";
  const pageMatches = () => location.origin === target.origin && location.pathname === target.pathname;
  const requestMatches = (url) => {{
    try {{
      const request = new URL(url, location.href);
      return pageMatches() && request.origin === target.origin &&
        request.pathname === "/api/_nuxt/product/fetch-packages-data" &&
        request.searchParams.get("prodMid") === productId;
    }} catch (_) {{ return false; }}
  }};
  const retain = (payload) => {{
    const observer = window.__kkdayPassivePackageObserver;
    // A successful transport alone is not authority for the resource graph.
    // KKday's normal frontend response must also report application success.
    if (!payload || (payload.message !== "success" && payload.result !== "BASE_SUCCESS")) {{
      observer.lastRejection = "app_success";
      return;
    }}
    const data = payload && payload.data;
    const setting = data && data["PRODUCT-SETTING"];
    // The observed contract exposes prod_mid as a JSON number.  A string is
    // deliberately rejected so a changed response shape cannot be accepted.
    if (!Number.isSafeInteger(setting?.prod_mid) || String(setting.prod_mid) !== productId) {{
      observer.lastRejection = "shape_product";
      return;
    }}
    const packageMap = data.PACKAGE;
    const itemMap = data.ITEM;
    if (!packageMap || typeof packageMap !== "object" || !itemMap || typeof itemMap !== "object") {{
      observer.lastRejection = "shape_maps";
      return;
    }}
    const packages = [];
    for (const [packageId, pkg] of Object.entries(packageMap)) {{
      if (!pkg || !Number.isSafeInteger(pkg.pkg_oid) || String(pkg.pkg_oid) !== packageId || !Array.isArray(pkg.items) || !pkg.items.length) {{
        observer.lastRejection = "shape_package";
        return;
      }}
      const itemIds = [];
      for (const itemId of pkg.items) {{
        const key = String(itemId);
        const item = itemMap[key];
        if (!item || !Number.isSafeInteger(item.item_oid) || String(item.item_oid) !== key) {{
          observer.lastRejection = "shape_item";
          return;
        }}
        itemIds.push(key);
      }}
      packages.push({{ packageId, name: String(pkg.name || ""), itemIds, description: "" }});
    }}
    if (!packages.length) {{ observer.lastRejection = "shape_empty"; return; }}
    window.__kkdayPassivePackageGraph = {{ productId, packages }};
    observer.accepted = true;
  }};
  const observe = (url, response) => {{
    const observer = window.__kkdayPassivePackageObserver;
    if (!requestMatches(url)) return;
    observer.events += 1;
    if (!response?.ok) {{ observer.lastRejection = "http"; return; }}
    response.clone().text().then((text) => retain(JSON.parse(text))).catch(() => {{ observer.lastRejection = "parse"; }});
  }};
  const fetch = window.fetch.bind(window);
  window.fetch = async (...args) => {{
    const response = await fetch(...args);
    observe(response.url, response);
    return response;
  }};
  const open = XMLHttpRequest.prototype.open;
  const send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) {{
    this.__kkdayPassiveGraphUrl = String(url);
    return open.call(this, method, url, ...rest);
  }};
  XMLHttpRequest.prototype.send = function(...args) {{
    this.addEventListener("loadend", () => {{
      const observer = window.__kkdayPassivePackageObserver;
      if (!requestMatches(this.__kkdayPassiveGraphUrl)) return;
      observer.events += 1;
      if (this.status < 200 || this.status >= 300) {{ observer.lastRejection = "http"; return; }}
      try {{
        // XHR may be configured for either JSON or text.  responseText throws
        // for responseType=json, so never make text-only assumptions here.
        const body = this.responseType === "json" ? this.response : this.responseText;
        retain(typeof body === "string" ? JSON.parse(body) : body);
      }} catch (_) {{ observer.lastRejection = "parse"; }}
    }}, {{ once: true }});
    return send.apply(this, args);
  }};
  window.__kkdayPassivePackageObserver = {{ installed: true, events: 0, accepted: false, lastRejection: "" }};
}})();
"""


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
        self._pending_passive_graph_url: str | None = None
        self._passive_package_graph: object = None

    @property
    def url(self) -> str:
        return self._url

    def goto(self, url: str, **kwargs: object) -> None:
        timeout_ms = int(kwargs.get("timeout") or self.bridge.config.request_timeout_ms)
        if self._pending_passive_graph_url == url:
            self._pending_passive_graph_url = None
            self._goto_with_passive_package_graph(url, timeout_ms)
            return
        result = self.bridge._task_call(
            f"""
await page.goto({json.dumps(url)}, {{ timeout: {timeout_ms} }})
cliLog({json.dumps(RESULT_MARKER)} + JSON.stringify({{ url: await page.url() }}))
""",
            timeout=max(30.0, timeout_ms / 1000 + 15),
        )
        self._url = str(result.get("url") or url)

    def arm_passive_package_graph(self, product_url: str) -> None:
        """Schedule a passive observer for the immediately following navigation.

        Arming, navigation, polling, and result retrieval must share one
        ``ego-browser nodejs`` invocation: a separate CLI call can lose the
        new-document observer's page heap before the graph is read.
        """
        self._pending_passive_graph_url = product_url

    def _goto_with_passive_package_graph(self, url: str, timeout_ms: int) -> None:
        source = json.dumps(passive_package_graph_init_source(url))
        result = self.bridge._task_call(
            f"""
await page.cdp("Page.addScriptToEvaluateOnNewDocument", {{ source: {source} }})
await page.goto({json.dumps(url)}, {{ timeout: {timeout_ms} }})
let passive = null;
let passiveDiagnostics = null;
for (let attempt = 0; attempt < 30; attempt += 1) {{
  // Function literals are executed by Ego; string expressions are data in
  // some Ego versions.  Keep retrieval in this same CLI invocation.
  passive = await page.evaluate(() => {{
    const graph = window.__kkdayPassivePackageGraph;
    const observer = window.__kkdayPassivePackageObserver;
    const heading = document.querySelector('h1');
    const h1 = String(heading?.textContent || '').trim();
    const diagnostics = {{
      observer: Boolean(observer?.installed), h1: Boolean(h1),
      eventCount: Number(observer?.events || 0),
      rejection: String(observer?.lastRejection || ''),
      graph: Boolean(graph?.packages?.length)
    }};
    if (!graph?.packages?.length || !h1) return {{ graph: null, diagnostics }};
    return {{ graph: {{
      productId: String(graph.productId || ''), url: location.href, name: h1,
      destination: '', rating: null, reviewCount: null, soldCount: null,
      wishlistCount: null, pageMinPrice: null, confirmation: '',
      cancellationPolicy: '', features: [], packages: graph.packages
    }}, diagnostics }};
  }});
  passiveDiagnostics = passive?.diagnostics || passiveDiagnostics;
  if (passive?.graph) break;
  await page.waitForTimeout(250);
}}
cliLog({json.dumps(RESULT_MARKER)} + JSON.stringify({{
  url: await page.url(), passiveGraph: passive?.graph || null,
  passiveDiagnostics: passiveDiagnostics || {{ observer: false, h1: false, eventCount: 0, rejection: '', graph: false }}
}}))
""",
            timeout=max(30.0, timeout_ms / 1000 + 20),
        )
        self._url = str(result.get("url") or url)
        self._passive_package_graph = result.get("passiveGraph")

    def read_passive_package_graph(self) -> object:
        return self._passive_package_graph

    def evaluate(self, expression: str, arg: object = None) -> object:
        argument = json.dumps(arg, ensure_ascii=False, default=str)
        source = json.dumps(f"({expression})({argument})")
        result = self.bridge._task_call(
            f"""
const source = {source}
// A function literal is executable in Ego.  The source stays data until this
// wrapper deliberately evaluates it in the page's own realm.
const value = await page.evaluate((source) => (0, eval)(source), source)
cliLog({json.dumps(RESULT_MARKER)} + JSON.stringify({{ value, url: await page.url() }}))
"""
        )
        self._url = str(result.get("url") or self._url)
        return result.get("value")

    def wait_for_function(self, expression: str, **kwargs: object) -> None:
        timeout_ms = int(kwargs.get("timeout") or self.bridge.config.request_timeout_ms)
        source = json.dumps(expression)
        self.bridge._task_call(
            f"""
const source = {source}
const value = await page.waitForFunction(source, undefined, {{ timeout: {timeout_ms} }})
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
            f"const task = await taskSpace({json.dumps(selector)})\n"
            f"const page = task.page('p1')\n{body}",
            timeout,
        )

    def connect(self) -> None:
        if self._connected:
            return
        homepage = market_homepage(self.config.market)
        result = self._task_call(
            f"""
await page.goto({json.dumps(homepage)}, {{ timeout: 60_000 }})
cliLog({json.dumps(RESULT_MARKER)} + JSON.stringify({{
  taskSpaceId: task.spaceId, taskSpaceName: task.name || {json.dumps(self.task_space_name)}, url: await page.url()
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
            f"const task = await taskSpace({json.dumps(selector)})\n"
            "await task.finish({ keep: [] })\n"
            f"cliLog({json.dumps(RESULT_MARKER)} + JSON.stringify({{ done: true }}))\n"
        )
        if result.get("done") is not True:
            raise EgoBrowserError("ego-browser task space 清理未完成")


BrowserSession = EgoBrowserBridge
