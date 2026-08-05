from pathlib import Path
import os

import pytest

from kkday_scraper.browser_bootstrap import (
    BrowserBootstrapError,
    BrowserBootstrapper,
    browser_binary,
    build_browser_command,
    parse_active_port_file,
)
from kkday_scraper.models import BrowserEndpoint, BrowserKind
from kkday_scraper.browser_session import SessionUnavailableError
import kkday_scraper.browser_bootstrap as browser_bootstrap_module


def test_edge_command_uses_dedicated_profile_and_debug_port(tmp_path: Path) -> None:
    command = build_browser_command(
        BrowserKind.EDGE,
        tmp_path,
        9222,
        "https://www.kkday.com/zh-tw",
    )

    assert command[0] == browser_binary(BrowserKind.EDGE)
    assert f"--remote-debugging-port=9222" in command
    assert f"--user-data-dir={tmp_path}" in command
    assert command[-1] == "https://www.kkday.com/zh-tw"
    assert "--user-data-dir=/Users" not in " ".join(command)


def test_parse_active_port_rejects_mismatched_port(tmp_path: Path) -> None:
    active_port = tmp_path / "DevToolsActivePort"
    active_port.write_text(
        "9222\n/devtools/browser/session\n", encoding="utf-8"
    )

    assert parse_active_port_file(
        active_port, BrowserKind.EDGE, tmp_path, expected_port=54423
    ) is None


def test_parse_active_port_returns_runtime_endpoint_without_safe_repr_leak(
    tmp_path: Path,
) -> None:
    active_port = tmp_path / "DevToolsActivePort"
    active_port.write_text(
        "9222\n/devtools/browser/session\n", encoding="utf-8"
    )

    endpoint = parse_active_port_file(
        active_port, BrowserKind.EDGE, tmp_path, expected_port=9222
    )

    assert endpoint == BrowserEndpoint(
        BrowserKind.EDGE,
        9222,
        "ws://127.0.0.1:9222/devtools/browser/session",
        tmp_path,
        False,
    )
    assert "session" not in repr(endpoint)


def test_running_dedicated_profile_is_reused_without_second_process(
    tmp_path: Path,
) -> None:
    profile = tmp_path / "edge"
    profile.mkdir()
    (profile / "DevToolsActivePort").write_text(
        "9222\n/devtools/browser/running-session\n", encoding="utf-8"
    )

    def fail_process(*_args, **_kwargs):
        raise AssertionError("a running dedicated profile must be reused")

    endpoint = BrowserBootstrapper(
        profile_root=tmp_path,
        process_factory=fail_process,
        reachable=lambda _url: None,
    ).start(BrowserKind.EDGE)

    assert endpoint.owns_process is False
    assert endpoint.profile_dir == profile
    assert endpoint.port == 9222


def test_stale_dedicated_profile_is_quarantined_before_relaunch(
    tmp_path: Path,
) -> None:
    profile = tmp_path / "edge"
    profile.mkdir()
    (profile / "DevToolsActivePort").write_text(
        "9222\n/devtools/browser/stale-session\n", encoding="utf-8"
    )
    process_calls = []

    class Process:
        def poll(self):
            return None

    def start_process(command, **kwargs):
        process_calls.append((command, kwargs))
        (profile / "DevToolsActivePort").write_text(
            "49233\n/devtools/browser/recovered-session\n", encoding="utf-8"
        )
        return Process()

    reachable_calls = 0
    def unreachable(_url):
        nonlocal reachable_calls
        reachable_calls += 1
        if reachable_calls == 1:
            raise SessionUnavailableError("not listening")

    endpoint = BrowserBootstrapper(
        profile_root=tmp_path,
        process_factory=start_process,
        port_factory=lambda: 49233,
        reachable=unreachable,
    ).start(BrowserKind.EDGE)

    assert endpoint.owns_process is True
    assert len(process_calls) == 1
    assert not list(profile.glob("DevToolsActivePort.stale-*"))


def test_new_profile_waits_for_matching_active_port_and_marks_owned_process(
    tmp_path: Path,
) -> None:
    profile = tmp_path / "edge"
    calls = []

    class Process:
        def poll(self):
            return None

    def start_process(command, **kwargs):
        calls.append((command, kwargs))
        profile.mkdir(parents=True, exist_ok=True)
        (profile / "DevToolsActivePort").write_text(
            "49231\n/devtools/browser/new-session\n", encoding="utf-8"
        )
        return Process()

    endpoint = BrowserBootstrapper(
        profile_root=tmp_path,
        process_factory=start_process,
        port_factory=lambda: 49231,
        reachable=lambda _url: None,
    ).start(BrowserKind.EDGE)

    assert endpoint.owns_process is True
    assert endpoint.port == 49231
    assert calls[0][1]["start_new_session"] is True
    assert f"--user-data-dir={profile}" in calls[0][0]


def test_browser_start_failure_does_not_fallback_to_another_browser(
    tmp_path: Path,
) -> None:
    calls = []

    def fail_process(command, **_kwargs):
        calls.append(command)
        raise OSError("permission denied")

    with pytest.raises(BrowserBootstrapError, match="无法启动 Edge"):
        BrowserBootstrapper(
            profile_root=tmp_path,
            process_factory=fail_process,
            port_factory=lambda: 49232,
        ).start(BrowserKind.EDGE)

    assert len(calls) == 1


def test_macos_singleton_symlink_uses_pid_without_opening_the_target(
    tmp_path: Path,
) -> None:
    profile = tmp_path / "edge"
    profile.mkdir()
    lock = profile / "SingletonLock"
    lock.symlink_to(f"test-host-{os.getpid()}")
    assert browser_bootstrap_module._profile_browser_locked(profile) is True

    lock.unlink()
    lock.symlink_to("test-host-99999999")
    assert browser_bootstrap_module._profile_browser_locked(profile) is False
