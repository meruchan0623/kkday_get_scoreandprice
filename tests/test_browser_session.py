from datetime import date
from pathlib import Path

import pytest

import kkday_scraper.browser_session as browser_session_module

from kkday_scraper.browser_session import (
    BrowserSession,
    _active_port_files,
    _sanitize_browser_error,
    classify_probe,
    browser_connection_info_for_cdp,
    ensure_cdp_endpoint_reachable,
    resolve_cdp_endpoint,
)
from kkday_scraper.models import BrowserEndpoint, BrowserKind, RunConfig


class FakePage:
    def __init__(self, probe: dict) -> None:
        self.probe = probe
        self.closed = False
        self.url = "https://www.kkday.com/zh-tw"

    def evaluate(self, _script: str, _args: dict) -> dict:
        return self.probe

    def close(self) -> None:
        self.closed = True


class BlankPage(FakePage):
    def __init__(self) -> None:
        super().__init__({})
        self.url = "about:blank"
        self.goto_calls = []

    def goto(self, url: str, **_kwargs) -> None:
        self.goto_calls.append(url)
        self.url = url


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
            "contractOk": True,
            "isLogin": True,
            "currency": "KRW",
        },
        "https://www.kkday.com/zh-tw/product/149025-example",
        "zh-tw",
    )

    assert probe.connected is True
    assert probe.member_api_ready is True
    assert probe.is_login is True
    assert probe.currency == "KRW"
    assert probe.block_reason is None
    assert not hasattr(probe, "cookie")


def test_connect_opens_the_configured_market_homepage(monkeypatch, tmp_path) -> None:
    page = BlankPage()

    class Context:
        def new_page(self):
            return page

    class Browser:
        contexts = [Context()]

    class Playwright:
        chromium = type(
            "Chromium",
            (),
            {"connect_over_cdp": staticmethod(lambda _url: Browser())},
        )()

        def stop(self):
            pass

    monkeypatch.setattr(browser_session_module, "ensure_cdp_endpoint_reachable", lambda _url: None)
    monkeypatch.setattr(browser_session_module, "resolve_cdp_endpoint", lambda _url: "ws://localhost/devtools/browser/test")
    monkeypatch.setattr(browser_session_module, "sync_playwright", lambda: type("Manager", (), {"start": lambda self: Playwright()})())

    session = BrowserSession(RunConfig(date(2026, 7, 22), tmp_path, market="zh-hk"))
    session.connect()

    assert page.goto_calls == ["https://www.kkday.com/zh-hk"]


def test_probe_member_switches_reused_page_to_requested_market_before_probe(
    monkeypatch, tmp_path
) -> None:
    class ReusedMarketPage(BlankPage):
        def __init__(self) -> None:
            super().__init__()
            self.url = "https://www.kkday.com/zh-tw/product/149025"
            self.operations = []

        def goto(self, url: str, **_kwargs) -> None:
            self.operations.append("goto")
            super().goto(url, **_kwargs)

        def evaluate(self, script: str, args: dict) -> dict:
            self.operations.append("evaluate")
            return {
                "status": 200,
                "contentType": "application/json",
                "contractOk": True,
                "isLogin": False,
                "currency": "HKD",
            }

    page = ReusedMarketPage()

    class Context:
        def new_page(self):
            return page

    class Browser:
        contexts = [Context()]

    class Playwright:
        chromium = type(
            "Chromium",
            (),
            {"connect_over_cdp": staticmethod(lambda _url: Browser())},
        )()

        def stop(self):
            pass

    monkeypatch.setattr(
        browser_session_module,
        "ensure_cdp_endpoint_reachable",
        lambda _url: None,
    )
    monkeypatch.setattr(
        browser_session_module,
        "resolve_cdp_endpoint",
        lambda _url: "ws://localhost/devtools/browser/test",
    )
    monkeypatch.setattr(
        browser_session_module,
        "sync_playwright",
        lambda: type("Manager", (), {"start": lambda self: Playwright()})(),
    )

    session = BrowserSession(
        RunConfig(date(2026, 7, 22), tmp_path, market="zh-hk")
    )
    session.connect()
    page.goto_calls.clear()
    page.operations.clear()
    page.url = "https://www.kkday.com/zh-tw/product/149025"
    probe = session.probe_member("zh-hk")

    assert page.goto_calls == ["https://www.kkday.com/zh-hk"]
    assert page.operations == ["goto", "evaluate"]
    assert probe.currency == "HKD"


def test_html_403_probe_is_blocked() -> None:
    probe = classify_probe(
        {
            "status": 403,
            "contentType": "text/html;charset=utf-8",
            "isLogin": False,
            "currency": "",
        },
        "https://www.kkday.com/zh-tw",
        "zh-tw",
    )

    assert probe.member_api_ready is False
    assert probe.block_reason == "KKday 返回 403/HTML，浏览器会话需要人工验证"


def test_json_probe_without_success_contract_is_not_ready() -> None:
    probe = classify_probe(
        {
            "status": 200,
            "contentType": "application/json",
            "contractOk": False,
            "isLogin": False,
            "currency": "",
        },
        "https://www.kkday.com/zh-tw",
        "zh-tw",
    )

    assert probe.member_api_ready is False
    assert probe.block_reason == "KKday 会话检测接口返回异常"


def test_attached_session_close_never_closes_user_browser(tmp_path: Path) -> None:
    page = FakePage({})
    browser = FakeBrowser()
    playwright = FakePlaywright()
    session = BrowserSession(RunConfig(date(2026, 7, 22), tmp_path))
    session._page = page
    session._browser = browser
    session._playwright = playwright
    session._owns_context = False

    session.close()

    assert page.closed is True
    assert browser.close_calls == 0
    assert playwright.stop_calls == 1


def test_attach_existing_does_not_read_or_inject_preference_cookies(
    tmp_path: Path, monkeypatch
) -> None:
    page = FakePage({})

    class Context:
        def add_cookies(self, _cookies):
            raise AssertionError("an attached user context must not be mutated")

        def new_page(self):
            return page

    context = Context()

    class Chromium:
        def connect_over_cdp(self, _endpoint):
            return type("Browser", (), {"contexts": [context]})()

    class PlaywrightRuntime:
        chromium = Chromium()

        def stop(self):
            pass

    monkeypatch.setattr(
        browser_session_module,
        "load_preference_cookies",
        lambda: (_ for _ in ()).throw(
            AssertionError("attach-existing must not read the preference store")
        ),
    )
    monkeypatch.setattr(
        browser_session_module,
        "ensure_cdp_endpoint_reachable",
        lambda _endpoint: None,
    )
    monkeypatch.setattr(
        browser_session_module,
        "resolve_cdp_endpoint",
        lambda _endpoint: "ws://127.0.0.1:9222/devtools/browser/attached",
    )
    monkeypatch.setattr(
        browser_session_module,
        "sync_playwright",
        lambda: type(
            "Starter", (), {"start": lambda self: PlaywrightRuntime()}
        )(),
    )

    session = BrowserSession(RunConfig(date(2026, 7, 22), tmp_path))
    session.connect()

    assert session.page is page


def test_explicit_dedicated_endpoint_injects_preference_cookies(
    tmp_path: Path, monkeypatch
) -> None:
    page = FakePage({})
    preference_cookies = [
        {
            "name": "currency",
            "value": "TWD",
            "domain": ".kkday.com",
            "path": "/",
            "secure": True,
            "httpOnly": False,
            "sameSite": "Lax",
        }
    ]

    class Context:
        def __init__(self):
            self.added_cookies = []

        def add_cookies(self, cookies):
            self.added_cookies.append(cookies)

        def new_page(self):
            return page

    context = Context()

    class Chromium:
        def connect_over_cdp(self, _endpoint):
            return type("Browser", (), {"contexts": [context]})()

    class PlaywrightRuntime:
        chromium = Chromium()

        def stop(self):
            pass

    monkeypatch.setattr(
        browser_session_module,
        "load_preference_cookies",
        lambda: preference_cookies,
    )
    monkeypatch.setattr(
        browser_session_module,
        "ensure_cdp_endpoint_reachable",
        lambda _endpoint: None,
    )
    monkeypatch.setattr(
        browser_session_module,
        "sync_playwright",
        lambda: type(
            "Starter", (), {"start": lambda self: PlaywrightRuntime()}
        )(),
    )
    endpoint = BrowserEndpoint(
        BrowserKind.EDGE,
        54423,
        "ws://127.0.0.1:54423/devtools/browser/dedicated",
        tmp_path,
        False,
    )

    session = BrowserSession(RunConfig(date(2026, 7, 22), tmp_path))
    session.connect(endpoint=endpoint)

    assert context.added_cookies == [preference_cookies]


def test_cdp_endpoint_uses_browser_active_port_websocket_path(
    tmp_path: Path,
) -> None:
    active_port = tmp_path / "DevToolsActivePort"
    active_port.write_text(
        "9222\n/devtools/browser/example-session-id\n", encoding="utf-8"
    )

    endpoint = resolve_cdp_endpoint(
        "http://127.0.0.1:9222", [active_port]
    )

    assert endpoint == "ws://127.0.0.1:9222/devtools/browser/example-session-id"


@pytest.mark.parametrize(
    "endpoint",
    [
        "ws://127.0.0.1:9222/devtools/browser/direct",
        "wss://localhost:9222/devtools/browser/direct",
        "http://192.0.2.10:9222",
        "ws://192.0.2.10:9222/devtools/browser/remote",
        "wss://192.0.2.10:9222/devtools/browser/remote",
    ],
)
def test_configured_cdp_endpoint_rejects_direct_websocket_and_remote_hosts(
    endpoint: str, tmp_path: Path
) -> None:
    with pytest.raises(
        browser_session_module.SessionUnavailableError,
        match="CDP|WebSocket|本机",
    ):
        resolve_cdp_endpoint(endpoint, [tmp_path / "DevToolsActivePort"])


def test_reachability_check_rejects_remote_endpoint_without_socket_access(
    monkeypatch,
) -> None:
    def fail_socket(*_args, **_kwargs):
        raise AssertionError("remote CDP must be rejected before socket access")

    monkeypatch.setattr(
        browser_session_module.socket, "create_connection", fail_socket
    )

    with pytest.raises(
        browser_session_module.SessionUnavailableError,
        match="本机",
    ):
        ensure_cdp_endpoint_reachable("ws://192.0.2.10:9222/devtools/browser/x")


def test_reachability_check_allows_internal_loopback_websocket(
    monkeypatch,
) -> None:
    connections = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    def connect(address, timeout):
        connections.append((address, timeout))
        return Connection()

    monkeypatch.setattr(
        browser_session_module.socket, "create_connection", connect
    )

    ensure_cdp_endpoint_reachable(
        "ws://127.0.0.1:54423/devtools/browser/dedicated"
    )

    assert connections == [(('127.0.0.1', 54423), 1.0)]


def test_reachability_check_rejects_non_browser_loopback_websocket(
    monkeypatch,
) -> None:
    def fail_socket(*_args, **_kwargs):
        raise AssertionError("invalid WebSocket path must fail before socket access")

    monkeypatch.setattr(
        browser_session_module.socket, "create_connection", fail_socket
    )

    with pytest.raises(
        browser_session_module.SessionUnavailableError,
        match="WebSocket",
    ):
        ensure_cdp_endpoint_reachable("ws://127.0.0.1:54423/not-devtools")


def test_default_active_port_scan_is_limited_to_dedicated_profiles(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        browser_session_module.Path,
        "home",
        classmethod(lambda _cls: tmp_path),
    )

    active_files = _active_port_files()

    dedicated_root = (
        tmp_path
        / "Library"
        / "Application Support"
        / "KKdayScraper"
        / "browser-profiles"
    )
    assert active_files == [
        dedicated_root / "edge" / "DevToolsActivePort",
        dedicated_root / "chrome" / "DevToolsActivePort",
    ]
    assert all("Google/Chrome" not in str(path) for path in active_files)
    assert all("Microsoft Edge" not in str(path) for path in active_files)


def test_explicit_empty_active_port_list_never_falls_back_to_default_scan(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        browser_session_module,
        "_active_port_files",
        lambda: (_ for _ in ()).throw(
            AssertionError("explicit empty discovery list must remain empty")
        ),
    )

    with pytest.raises(
        browser_session_module.SessionUnavailableError,
        match="无法发现 WebSocket 地址",
    ):
        resolve_cdp_endpoint("http://127.0.0.1:54423", [])


def test_active_port_websocket_path_rejects_control_characters(
    tmp_path: Path,
) -> None:
    active_port = tmp_path / "DevToolsActivePort"
    active_port.write_bytes(
        b"54423\n/devtools/browser/session-id\x00suffix\n"
    )

    with pytest.raises(
        browser_session_module.SessionUnavailableError,
        match="无法发现 WebSocket 地址",
    ):
        resolve_cdp_endpoint("http://127.0.0.1:54423", [active_port])


def test_browser_error_does_not_expose_devtools_websocket_identifier() -> None:
    message = _sanitize_browser_error(
        "connect ws://127.0.0.1:9222/devtools/browser/secret-session-id failed"
    )

    assert "secret-session-id" not in message
    assert "<redacted>" in message


def test_session_attach_failure_never_launches_fallback_browser(
    tmp_path: Path, monkeypatch
) -> None:
    class FailingChromium:
        def __init__(self) -> None:
            self.launch_calls = 0

        def connect_over_cdp(self, _endpoint):
            raise RuntimeError("CDP permission denied")

        def launch_persistent_context(self, *_args, **_kwargs):
            self.launch_calls += 1
            raise AssertionError("fallback browser must not launch")

    chromium = FailingChromium()

    class FakePlaywrightRuntime:
        def __init__(self) -> None:
            self.chromium = chromium

        def stop(self) -> None:
            pass

    class FakeStarter:
        def start(self):
            return FakePlaywrightRuntime()

    monkeypatch.setattr(
        browser_session_module, "sync_playwright", lambda: FakeStarter()
    )
    monkeypatch.setattr(
        browser_session_module,
        "resolve_cdp_endpoint",
        lambda _endpoint: "ws://127.0.0.1:9222/devtools/browser/test",
    )
    monkeypatch.setattr(
        browser_session_module,
        "ensure_cdp_endpoint_reachable",
        lambda _endpoint: None,
    )
    session = BrowserSession(RunConfig(date(2026, 7, 22), tmp_path))

    with pytest.raises(
        browser_session_module.SessionUnavailableError,
        match="无法连接现有 CDP 浏览器",
    ):
        session.connect()

    assert chromium.launch_calls == 0


def test_session_passes_only_runtime_websocket_to_playwright(
    tmp_path: Path, monkeypatch
) -> None:
    page = FakePage({})

    class Context:
        def __init__(self):
            self.pages = []

        def new_page(self):
            self.pages.append(page)
            return page

    class Chromium:
        def __init__(self):
            self.endpoints = []
            self.context = Context()

        def connect_over_cdp(self, endpoint):
            self.endpoints.append(endpoint)
            return type("Browser", (), {"contexts": [self.context]})()

    chromium = Chromium()

    class PlaywrightRuntime:
        def __init__(self):
            self.chromium = chromium

        def stop(self):
            pass

    class Starter:
        def start(self):
            return PlaywrightRuntime()

    monkeypatch.setattr(
        browser_session_module, "sync_playwright", lambda: Starter()
    )
    monkeypatch.setattr(
        browser_session_module, "load_preference_cookies", lambda: []
    )
    reachable = []
    monkeypatch.setattr(
        browser_session_module,
        "ensure_cdp_endpoint_reachable",
        lambda endpoint: reachable.append(endpoint),
    )
    endpoint = BrowserEndpoint(
        BrowserKind.CHROME,
        54423,
        "ws://127.0.0.1:54423/devtools/browser/runtime-only",
        tmp_path,
        True,
    )
    session = BrowserSession(RunConfig(date(2026, 7, 22), tmp_path))

    session.connect(endpoint=endpoint)

    assert chromium.endpoints == [endpoint.ws_url]
    assert reachable == [endpoint.ws_url]
    session.close()


def test_unreachable_cdp_port_has_actionable_existing_browser_message(
    monkeypatch,
) -> None:
    def refuse_connection(*_args, **_kwargs):
        raise OSError("Connection refused")

    monkeypatch.setattr(browser_session_module.socket, "create_connection", refuse_connection)

    with pytest.raises(
        browser_session_module.SessionUnavailableError,
        match="9222 未监听.*chrome://inspect/#remote-debugging",
    ):
        ensure_cdp_endpoint_reachable("http://127.0.0.1:9222")


def test_active_port_file_is_the_source_of_websocket_endpoint(tmp_path: Path) -> None:
    active_port = tmp_path / "DevToolsActivePort"
    active_port.write_text(
        "54423\n/devtools/browser/chrome-session\n", encoding="utf-8"
    )

    endpoint = resolve_cdp_endpoint(
        "http://127.0.0.1:54423", [active_port]
    )

    assert endpoint == "ws://127.0.0.1:54423/devtools/browser/chrome-session"


def test_existing_cdp_identity_is_safe_and_does_not_include_websocket_id(
    tmp_path: Path,
) -> None:
    active_port = tmp_path / "Google" / "Chrome" / "DevToolsActivePort"
    active_port.parent.mkdir(parents=True)
    active_port.write_text(
        "54423\n/devtools/browser/private-session\n", encoding="utf-8"
    )

    info = browser_connection_info_for_cdp(
        "http://127.0.0.1:54423", [active_port]
    )

    assert info is not None
    assert info.browser is BrowserKind.CHROME
    assert info.port == 54423
    assert "private-session" not in repr(info)


@pytest.mark.parametrize(
    ("profile_name", "expected_browser"),
    [
        ("edge", BrowserKind.EDGE),
        ("chrome", BrowserKind.CHROME),
    ],
)
def test_dedicated_profile_identity_preserves_browser_kind(
    tmp_path: Path,
    profile_name: str,
    expected_browser: BrowserKind,
) -> None:
    active_port = tmp_path / profile_name / "DevToolsActivePort"
    active_port.parent.mkdir(parents=True)
    active_port.write_text(
        "54423\n/devtools/browser/private-session\n", encoding="utf-8"
    )

    info = browser_connection_info_for_cdp(
        "http://127.0.0.1:54423", [active_port]
    )

    assert info is not None
    assert info.browser is expected_browser


def test_http_endpoint_without_active_port_never_reaches_playwright(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        browser_session_module.SessionUnavailableError,
        match="无法发现 WebSocket 地址",
    ):
        resolve_cdp_endpoint(
            "http://127.0.0.1:54423",
            [tmp_path / "missing-DevToolsActivePort"],
        )
