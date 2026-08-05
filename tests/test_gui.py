import pytest

from kkday_scraper.gui import KKdayScraperApp
from kkday_scraper.models import RunPhase


class FakeRoot:
    def __init__(self) -> None:
        self.callbacks = []
        self.destroy_calls = 0

    def after(self, _delay: int, callback) -> None:
        self.callbacks.append(callback)

    def destroy(self) -> None:
        self.destroy_calls += 1


class FakeWorker:
    def __init__(self) -> None:
        self.shutdown_calls = 0
        self.alive = True

    def shutdown(self) -> None:
        self.shutdown_calls += 1

    def is_alive(self) -> bool:
        return self.alive


class FakeVar:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def set(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


def test_close_waits_for_worker_flush_before_destroying_root() -> None:
    app = KKdayScraperApp.__new__(KKdayScraperApp)
    app.root = FakeRoot()
    app.worker = FakeWorker()
    app.phase = RunPhase.IDLE
    app._closing = False
    app.status_var = FakeVar()
    app._apply_policy = lambda: None

    app._on_close()

    assert app.worker.shutdown_calls == 1
    assert app.root.destroy_calls == 0
    assert len(app.root.callbacks) == 1

    app.worker.alive = False
    app.root.callbacks.pop()()
    assert app.root.destroy_calls == 1


def test_config_rejects_an_empty_output_directory() -> None:
    app = KKdayScraperApp.__new__(KKdayScraperApp)
    app.date_var = FakeVar("2026-07-22")
    app.port_var = FakeVar("9222")
    app.output_var = FakeVar("")
    app.market_var = FakeVar("zh-tw")

    with pytest.raises(ValueError, match="输出目录不能为空"):
        app._config()


def test_config_accepts_zh_hk_market(tmp_path) -> None:
    app = KKdayScraperApp.__new__(KKdayScraperApp)
    app.date_var = FakeVar("2026-07-22")
    app.port_var = FakeVar("9222")
    app.output_var = FakeVar(str(tmp_path))
    app.market_var = FakeVar("zh-hk")

    assert app._config().market == "zh-hk"
