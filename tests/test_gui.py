from datetime import date, timedelta

import pytest

import kkday_scraper.gui as gui_module
from kkday_scraper.gui import KKdayScraperApp, default_usage_date
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


def test_gui_defaults_to_next_calendar_day() -> None:
    assert default_usage_date(date(2026, 8, 6)) == date(2026, 8, 7)
    assert default_usage_date(date(2026, 8, 6)) == date(2026, 8, 6) + timedelta(days=1)


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


def test_close_stops_waiting_after_the_shutdown_budget(monkeypatch) -> None:
    now = [100.0]
    monkeypatch.setattr(gui_module, "monotonic", lambda: now[0])
    app = KKdayScraperApp.__new__(KKdayScraperApp)
    app.root = FakeRoot()
    app.worker = FakeWorker()
    app.phase = RunPhase.IDLE
    app._closing = False
    app.status_var = FakeVar()
    app._apply_policy = lambda: None

    app._on_close()
    now[0] += gui_module.CLOSE_WAIT_SECONDS + 0.1
    app.root.callbacks.pop()()

    assert app.worker.alive is True
    assert app.root.destroy_calls == 1
    assert "超时" in app.status_var.get()


def test_config_rejects_an_empty_output_directory() -> None:
    app = KKdayScraperApp.__new__(KKdayScraperApp)
    app.date_var = FakeVar("2026-07-22")
    app.task_space_var = FakeVar("kkday-sku-price-zh-tw")
    app.output_var = FakeVar("")
    app.market_var = FakeVar("zh-tw")

    with pytest.raises(ValueError, match="输出目录不能为空"):
        app._config()


def test_config_accepts_zh_hk_market(tmp_path) -> None:
    app = KKdayScraperApp.__new__(KKdayScraperApp)
    app.date_var = FakeVar("2026-07-22")
    app.task_space_var = FakeVar("kkday-hk")
    app.output_var = FakeVar(str(tmp_path))
    app.market_var = FakeVar("zh-hk")

    assert app._config().market == "zh-hk"
    assert app._config().ego_task_space == "kkday-hk"


def test_gui_rolls_an_untouched_automatic_default_forward(monkeypatch) -> None:
    monkeypatch.setattr(gui_module, "default_usage_date", lambda: date(2026, 9, 1))
    app = KKdayScraperApp.__new__(KKdayScraperApp)
    app.date_var = FakeVar("2026-08-31")
    app._automatic_usage_date = True
    app._setting_automatic_usage_date = False

    app._refresh_automatic_usage_date()

    assert app.date_var.get() == "2026-09-01"


def test_gui_preserves_a_user_selected_date(monkeypatch) -> None:
    monkeypatch.setattr(gui_module, "default_usage_date", lambda: date(2026, 9, 1))
    app = KKdayScraperApp.__new__(KKdayScraperApp)
    app.date_var = FakeVar("2026-08-31")
    app._automatic_usage_date = False
    app._setting_automatic_usage_date = False

    app._refresh_automatic_usage_date()

    assert app.date_var.get() == "2026-08-31"
