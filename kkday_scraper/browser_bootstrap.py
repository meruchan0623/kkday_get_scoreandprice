from __future__ import annotations

import os
import platform
import socket
import subprocess
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Callable

try:
    import fcntl
except ImportError:  # pragma: no cover - macOS is the supported platform
    fcntl = None

from .browser_session import SessionUnavailableError, ensure_cdp_endpoint_reachable
from .models import BrowserEndpoint, BrowserKind


DEFAULT_KKDAY_URL = "https://www.kkday.com/zh-tw"
DEFAULT_PROFILE_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "KKdayScraper"
    / "browser-profiles"
)

_BROWSER_BINARIES = {
    BrowserKind.EDGE: Path(
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
    ),
    BrowserKind.CHROME: Path(
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    ),
}


class BrowserBootstrapError(RuntimeError):
    """A safe, actionable failure while starting or reusing a browser."""


def _installed_kinds() -> tuple[BrowserKind, ...]:
    if platform.system() != "Darwin":
        return ()
    return tuple(
        kind for kind, binary in _BROWSER_BINARIES.items() if binary.exists()
    )


def select_browser(kind: BrowserKind) -> BrowserKind:
    if kind is not BrowserKind.AUTO:
        if _BROWSER_BINARIES[kind].exists():
            return kind
        raise BrowserBootstrapError(f"未找到 {kind.value.title()} 浏览器")
    installed = _installed_kinds()
    if installed:
        return installed[0]
    raise BrowserBootstrapError("未找到可用的 Edge 或 Chrome 浏览器")


def browser_binary(kind: BrowserKind) -> str:
    selected = select_browser(kind)
    return str(_BROWSER_BINARIES[selected])


def profile_dir_for(
    kind: BrowserKind, root: Path | None = None
) -> Path:
    selected = select_browser(kind)
    return (root or DEFAULT_PROFILE_ROOT) / selected.value


def active_port_file_for(profile_dir: Path) -> Path:
    return profile_dir / "DevToolsActivePort"


def build_browser_command(
    kind: BrowserKind,
    profile_dir: Path,
    port: int,
    homepage: str = DEFAULT_KKDAY_URL,
) -> tuple[str, ...]:
    selected = select_browser(kind)
    return (
        str(_BROWSER_BINARIES[selected]),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--lang=zh-TW",
        homepage,
    )


def parse_active_port_file(
    path: Path,
    browser: BrowserKind,
    profile_dir: Path,
    expected_port: int | None = None,
) -> BrowserEndpoint | None:
    """Parse Chromium's two-line DevToolsActivePort file.

    The session id is used only to build the in-memory endpoint.  It is never
    included in the endpoint representation or any user-facing message.
    """

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        port = int(lines[0].strip())
        ws_path = lines[1].strip()
    except (OSError, ValueError, IndexError):
        return None
    if not 1 <= port <= 65535:
        return None
    if expected_port is not None and port != expected_port:
        return None
    if not ws_path.startswith("/devtools/browser/"):
        return None
    if any(char in ws_path for char in "\r\n\x00"):
        return None
    return BrowserEndpoint(
        browser=browser,
        port=port,
        ws_url=f"ws://127.0.0.1:{port}{ws_path}",
        profile_dir=profile_dir,
        owns_process=False,
    )


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def _profile_start_lock(profile_dir: Path):
    """Serialize bootstrap checks without touching Chromium login files."""

    lock_file = profile_dir / ".kkday-scraper-bootstrap.lock"
    handle = lock_file.open("a+")
    try:
        if fcntl is not None:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise BrowserBootstrapError(
                    "专用 Profile 正在被另一个启动流程使用，请稍后重试"
                ) from exc
        yield
    finally:
        if fcntl is not None:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()


def _profile_browser_locked(profile_dir: Path) -> bool:
    """Return whether Chromium still owns its macOS SingletonLock."""

    lock_file = profile_dir / "SingletonLock"
    if not os.path.lexists(lock_file):
        return False
    try:
        target = os.readlink(lock_file)
    except OSError:
        # A regular lock file is treated conservatively as occupied.
        return True
    try:
        pid = int(target.rsplit("-", 1)[-1])
    except (TypeError, ValueError):
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _quarantine_active_port_file(path: Path) -> None:
    try:
        path.unlink()
    except OSError as exc:
        raise BrowserBootstrapError(
            "无法清理过期的 DevToolsActivePort，请检查专用 Profile 权限"
        ) from exc


class BrowserBootstrapper:
    """Start or reuse one dedicated persistent KKday browser profile."""

    def __init__(
        self,
        *,
        profile_root: Path | None = None,
        process_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
        port_factory: Callable[[], int] = find_free_port,
        reachable: Callable[[str], None] = ensure_cdp_endpoint_reachable,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        timeout: float = 30.0,
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        self.profile_root = profile_root or DEFAULT_PROFILE_ROOT
        self.process_factory = process_factory
        self.port_factory = port_factory
        self.reachable = reachable
        self.clock = clock
        self.sleep = sleep
        self.timeout = timeout
        self.cancelled = cancelled

    def start(
        self,
        requested: BrowserKind = BrowserKind.AUTO,
        homepage: str = DEFAULT_KKDAY_URL,
    ) -> BrowserEndpoint:
        selected = select_browser(requested)
        profile_dir = profile_dir_for(selected, self.profile_root)
        profile_dir.mkdir(parents=True, exist_ok=True)
        with _profile_start_lock(profile_dir):
            return self._start_locked(selected, profile_dir, homepage)

    def _start_locked(
        self,
        selected: BrowserKind,
        profile_dir: Path,
        homepage: str,
    ) -> BrowserEndpoint:
        active_file = active_port_file_for(profile_dir)

        if active_file.exists():
            existing = parse_active_port_file(
                active_file, selected, profile_dir
            )
            if existing is None:
                if _profile_browser_locked(profile_dir):
                    raise BrowserBootstrapError(
                        "专用 Profile 已运行但调试状态无效，请关闭该专用窗口后重试"
                    )
                _quarantine_active_port_file(active_file)
            else:
                try:
                    self.reachable(existing.ws_url)
                except SessionUnavailableError as exc:
                    if _profile_browser_locked(profile_dir):
                        raise BrowserBootstrapError(
                            f"专用 {selected.value.title()} Profile 已运行但 CDP 不可用，"
                            "请关闭该专用窗口后重试"
                        ) from exc
                    _quarantine_active_port_file(active_file)
                else:
                    return existing
        elif _profile_browser_locked(profile_dir):
            raise BrowserBootstrapError(
                f"专用 {selected.value.title()} Profile 已运行但没有有效调试地址"
            )

        # Chromium only persists DevToolsActivePort reliably when it selects
        # the ephemeral port itself.  A fixed port can briefly listen without
        # leaving the discovery file that this bootstrap contract requires.
        port = 0
        command = build_browser_command(selected, profile_dir, port, homepage)
        try:
            process = self.process_factory(
                list(command),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise BrowserBootstrapError(
                f"无法启动 {selected.value.title()} 调试浏览器：{exc}"
            ) from exc

        deadline = self.clock() + self.timeout
        while self.clock() < deadline:
            if self.cancelled is not None and self.cancelled():
                terminate = getattr(process, "terminate", None)
                if callable(terminate):
                    terminate()
                raise BrowserBootstrapError("浏览器启动已停止")
            endpoint = parse_active_port_file(
                active_file,
                selected,
                profile_dir,
                expected_port=None,
            )
            if endpoint is not None:
                try:
                    self.reachable(endpoint.ws_url)
                except SessionUnavailableError:
                    pass
                else:
                    return replace(endpoint, owns_process=True)
            if process.poll() is not None:
                raise BrowserBootstrapError(
                    f"{selected.value.title()} 调试浏览器启动后立即退出，"
                    "请检查专用 Profile 或系统浏览器权限"
                )
            self.sleep(0.2)

        terminate = getattr(process, "terminate", None)
        if callable(terminate):
            terminate()
        raise BrowserBootstrapError(
            f"{selected.value.title()} 调试端口未在预期时间内就绪，"
            "请重试或检查浏览器是否已被安全软件拦截"
        )
