from __future__ import annotations

import re
import socket
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)

from .cookie_store import load_preference_cookies
from .models import (
    BrowserConnectionInfo,
    BrowserEndpoint,
    BrowserKind,
    RunConfig,
    SessionProbe,
    market_homepage,
)


class SessionUnavailableError(RuntimeError):
    pass


_LOOPBACK_CDP_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_BROWSER_WEBSOCKET_PATH_PREFIX = "/devtools/browser/"


def _sanitize_browser_error(message: str) -> str:
    return re.sub(
        r"(wss?://(?:127\.0\.0\.1|localhost|\[::1\]):\d+/devtools/browser/)[^\s'\"<>]+",
        r"\1<redacted>",
        message,
    )


def _parse_loopback_cdp_url(
    cdp_url: str, *, allowed_schemes: frozenset[str]
):
    try:
        parsed = urlsplit(cdp_url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise SessionUnavailableError("CDP 地址无效") from exc
    if parsed.scheme not in allowed_schemes:
        raise SessionUnavailableError("CDP 地址协议无效")
    if parsed.username is not None or parsed.password is not None:
        raise SessionUnavailableError("CDP 地址不得包含用户信息")
    if hostname not in _LOOPBACK_CDP_HOSTS:
        raise SessionUnavailableError("CDP 连接仅允许使用本机 loopback 地址")
    if port is None:
        raise SessionUnavailableError("CDP 端口无效")
    return parsed, hostname, port


def _is_safe_browser_websocket_path(path: str) -> bool:
    return (
        path.startswith(_BROWSER_WEBSOCKET_PATH_PREFIX)
        and len(path) > len(_BROWSER_WEBSOCKET_PATH_PREFIX)
        and not any(ord(char) < 32 or ord(char) == 127 for char in path)
        and "?" not in path
        and "#" not in path
    )


def ensure_cdp_endpoint_reachable(cdp_url: str, timeout: float = 1.0) -> None:
    parsed, hostname, port = _parse_loopback_cdp_url(
        cdp_url, allowed_schemes=frozenset({"http", "ws"})
    )
    if parsed.scheme == "ws" and (
        not _is_safe_browser_websocket_path(parsed.path)
        or parsed.query
        or parsed.fragment
    ):
        raise SessionUnavailableError("CDP WebSocket 地址路径无效")
    socket_host = "::1" if hostname == "::1" else "127.0.0.1"
    try:
        with socket.create_connection((socket_host, port), timeout=timeout):
            return
    except OSError as exc:
        raise SessionUnavailableError(
            f"{hostname}:{port} 未监听。请保持现有 Chrome/Edge 打开，在 "
            "chrome://inspect/#remote-debugging（Edge 可用 "
            "edge://inspect/#remote-debugging）勾选 Allow remote debugging，"
            "然后点击“连接现有浏览器”。程序不会启动备用浏览器。"
        ) from exc


def _active_port_files() -> list[Path]:
    root = (
        Path.home()
        / "Library"
        / "Application Support"
        / "KKdayScraper"
        / "browser-profiles"
    )
    return [
        root / "edge" / "DevToolsActivePort",
        root / "chrome" / "DevToolsActivePort",
    ]


def resolve_cdp_endpoint(
    cdp_url: str, active_port_files: list[Path] | None = None
) -> str:
    """Resolve Chrome's browser WebSocket without exposing its transient id."""

    try:
        parsed = urlsplit(cdp_url)
    except ValueError as exc:
        raise SessionUnavailableError("CDP 地址无效") from exc
    if parsed.scheme in {"ws", "wss"}:
        raise SessionUnavailableError(
            "CDP 配置不得直接使用 WebSocket 地址；"
            "请配置本机 HTTP 调试端口并通过 DevToolsActivePort 发现"
        )
    parsed, _hostname, requested_port = _parse_loopback_cdp_url(
        cdp_url, allowed_schemes=frozenset({"http"})
    )
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise SessionUnavailableError("CDP HTTP 配置只能指向本机调试端口")

    discovery_files = (
        _active_port_files()
        if active_port_files is None
        else active_port_files
    )
    for active_port_file in discovery_files:
        try:
            lines = active_port_file.read_text(encoding="utf-8").splitlines()
            port = int(lines[0])
            path = lines[1]
        except (OSError, ValueError, IndexError):
            continue
        if port == requested_port and _is_safe_browser_websocket_path(path):
            return f"ws://127.0.0.1:{port}{path}"
    raise SessionUnavailableError(
        f"调试端口 {requested_port} 存在但无法发现 WebSocket 地址；"
        "请重新启动一键调试浏览器或确认 DevToolsActivePort 未过期"
    )


def browser_connection_info_for_cdp(
    cdp_url: str, active_port_files: list[Path] | None = None
) -> BrowserConnectionInfo | None:
    """Return safe browser identity without returning its WebSocket URL."""

    try:
        _parsed, _hostname, port = _parse_loopback_cdp_url(
            cdp_url, allowed_schemes=frozenset({"http"})
        )
    except SessionUnavailableError:
        return None
    discovery_files = (
        _active_port_files()
        if active_port_files is None
        else active_port_files
    )
    for active_port_file in discovery_files:
        try:
            active_port = int(
                active_port_file.read_text(encoding="utf-8")
                .splitlines()[0]
                .strip()
            )
        except (OSError, ValueError, IndexError):
            continue
        if active_port != port:
            continue
        path_text = str(active_port_file).lower()
        profile_name = active_port_file.parent.name.lower()
        if profile_name == "edge" or (
            "microsoft" in path_text and "edge" in path_text
        ):
            browser = BrowserKind.EDGE
        elif profile_name == "chrome" or "google" in path_text or "chrome" in path_text:
            browser = BrowserKind.CHROME
        else:
            browser = BrowserKind.AUTO
        return BrowserConnectionInfo(
            browser=browser,
            port=port,
            profile_dir=active_port_file.parent,
            owns_process=False,
        )
    return None


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
    contractOk: Boolean(
      data && data.data &&
      (data.message === "success" || data.result === "BASE_SUCCESS")
    ),
    isLogin: Boolean(data && data.data && data.data.isLogin),
    currency: data && data.data && data.data.currency ? String(data.data.currency) : ""
  };
}
"""


def classify_probe(
    raw: dict[str, Any], page_url: str, market: str
) -> SessionProbe:
    status = int(raw.get("status") or 0)
    content_type = str(raw.get("contentType") or "").lower()
    blocked = status in {401, 403} or "text/html" in content_type
    contract_ok = bool(raw.get("contractOk"))
    if blocked:
        reason = "KKday 返回 403/HTML，浏览器会话需要人工验证"
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


class BrowserSession:
    """Own a scraper page without taking ownership of an attached user browser."""

    def __init__(self, config: RunConfig) -> None:
        self.config = config
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

    def _inject_preference_cookies(self) -> None:
        cookies = load_preference_cookies()
        if not cookies:
            return
        try:
            self._context.add_cookies(cookies)
        except Exception:
            # Non-fatal: probe_member will still detect a mismatch and we can
            # surface it. Bad cookies must never crash the dedicated path.
            pass

    def connect(
        self,
        allow_launch: bool = False,
        endpoint: BrowserEndpoint | None = None,
    ) -> None:
        if self._page is not None:
            return
        if allow_launch:
            raise SessionUnavailableError(
                "浏览器启动必须通过一键启动调试浏览器，"
                "不会自动启动或复制默认浏览器 Profile"
            )
        if endpoint is not None:
            cdp_endpoint = endpoint.ws_url
            inject_preference_cookies = True
        else:
            cdp_endpoint = resolve_cdp_endpoint(self.config.cdp_url)
            inject_preference_cookies = False
        ensure_cdp_endpoint_reachable(cdp_endpoint)
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.connect_over_cdp(
                cdp_endpoint
            )
            if not self._browser.contexts:
                raise SessionUnavailableError("CDP 浏览器没有可复用的默认上下文")
            self._context = self._browser.contexts[0]
            if inject_preference_cookies:
                self._inject_preference_cookies()
            self._page = self._context.new_page()
            self._owns_context = False
        except Exception as attach_error:
            self.close()
            raise SessionUnavailableError(
                "无法连接现有 CDP 浏览器："
                f"{_sanitize_browser_error(str(attach_error))}"
            ) from attach_error

        if not self.page.url.startswith("https://www.kkday.com/"):
            self.page.goto(
                market_homepage(self.config.market),
                wait_until="domcontentloaded",
                timeout=60_000,
            )

    def probe_member(self, market: str) -> SessionProbe:
        # A dedicated browser can be reused from another KKday subsite.
        # Probe only after entering the requested market's homepage.
        self.page.goto(
            market_homepage(market),
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        raw = self.page.evaluate(PROBE_SCRIPT, {"market": market})
        if not isinstance(raw, dict):
            raise SessionUnavailableError("浏览器会话检测返回了未知结构")
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
