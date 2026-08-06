from datetime import date, datetime
from pathlib import Path
from threading import Event, get_ident, main_thread

from kkday_scraper.browser_api import SessionBlockedError
from kkday_scraper.models import (
    AppEvent,
    BrowserConnectionInfo,
    BrowserEndpoint,
    BrowserKind,
    EventKind,
    InputItem,
    ProductResult,
    FailureKind,
    FailureRecord,
    RunConfig,
    RunPhase,
    RunResult,
    ReadinessReport,
    SessionProbe,
)
from kkday_scraper.task_runner import RunControl, TaskRunner, WorkerService


class FakeSession:
    def __init__(self, blocked_on_probe: int | None = None) -> None:
        self.probe_calls = 0
        self.blocked_on_probe = blocked_on_probe
        self.page = object()

    def probe_member(self, market: str) -> SessionProbe:
        self.probe_calls += 1
        if self.blocked_on_probe == self.probe_calls:
            return SessionProbe(
                True,
                False,
                True,
                "KRW",
                market,
                "https://www.kkday.com",
                "blocked",
            )
        return SessionProbe(
            True,
            True,
            True,
            "KRW",
            market,
            "https://www.kkday.com",
        )


class FakeScraper:
    def __init__(self, blocked_url: str | None = None) -> None:
        self.blocked_url = blocked_url
        self.calls: list[str] = []
        self.readiness_reporter = lambda _report: None

    def scrape(
        self, item: InputItem, _probe: SessionProbe, _config: RunConfig
    ) -> ProductResult:
        self.calls.append(item.url)
        if item.url == self.blocked_url:
            raise SessionBlockedError("403")
        self.readiness_reporter(
            ReadinessReport(
                True,
                True,
                True,
                True,
                True,
                item.url,
                "KRW",
            )
        )
        return ProductResult(item, None, ())


def test_runner_checkpoints_after_each_product(tmp_path: Path) -> None:
    items = [
        InputItem("https://www.kkday.com/zh-tw/product/1-a", input_order=0),
        InputItem("https://www.kkday.com/zh-tw/product/2-b", input_order=1),
    ]
    session = FakeSession()
    scraper = FakeScraper()
    checkpoints: list[int] = []
    events = []
    runner = TaskRunner(
        session,
        lambda _page, _config, _continue: scraper,
        sleep=lambda _seconds: None,
        uniform=lambda low, _high: low,
    )

    result = runner.run(
        items,
        RunConfig(date(2026, 7, 22), tmp_path),
        RunControl(),
        events.append,
        lambda products, final: checkpoints.append(len(products))
        or (tmp_path / "result.xlsx" if final else None),
    )

    assert scraper.calls == [items[0].url, items[1].url]
    assert checkpoints == [1, 2, 2]
    assert result.stopped is False
    assert result.terminal_phase is RunPhase.COMPLETED
    assert result.requested_count == 2
    assert result.processed_count == 2
    assert result.final_checkpoint_saved is True
    assert events[-1].kind is EventKind.FINISHED
    assert events[-1].phase is RunPhase.COMPLETED


def test_runner_stops_batch_on_session_block_and_keeps_partial_result(
    tmp_path: Path,
) -> None:
    first = InputItem(
        "https://www.kkday.com/zh-tw/product/1-a", input_order=0
    )
    second = InputItem(
        "https://www.kkday.com/zh-tw/product/2-b", input_order=1
    )
    third = InputItem(
        "https://www.kkday.com/zh-tw/product/3-c", input_order=2
    )
    session = FakeSession()
    scraper = FakeScraper(blocked_url=second.url)
    events = []
    runner = TaskRunner(
        session,
        lambda _page, _config, _continue: scraper,
        sleep=lambda _seconds: None,
        uniform=lambda low, _high: low,
    )

    result = runner.run(
        [first, second, third],
        RunConfig(date(2026, 7, 22), tmp_path),
        RunControl(),
        events.append,
        lambda _products, _final: None,
    )

    assert scraper.calls == [first.url, second.url]
    assert len(result.products) == 2
    assert result.products[-1].failures[0].kind is FailureKind.SESSION_BLOCKED
    assert events[-1].phase is RunPhase.BLOCKED


def test_runner_records_unavailable_member_probe_as_current_product_failure(
    tmp_path: Path,
) -> None:
    first = InputItem("https://www.kkday.com/zh-tw/product/1-a", input_order=0)
    second = InputItem("https://www.kkday.com/zh-tw/product/2-b", input_order=1)
    checkpoints: list[tuple[int, bool]] = []
    events = []
    runner = TaskRunner(
        FakeSession(blocked_on_probe=2),
        lambda _page, _config, _continue: FakeScraper(),
        sleep=lambda _seconds: None,
    )

    result = runner.run(
        [first, second],
        RunConfig(date(2026, 7, 22), tmp_path),
        RunControl(),
        events.append,
        lambda products, final: checkpoints.append((len(products), final))
        or (tmp_path / "result.xlsx" if final else None),
    )

    assert result.terminal_phase is RunPhase.BLOCKED
    assert result.requested_count == 2
    assert result.processed_count == 2
    assert result.final_checkpoint_saved is True
    assert [failure.url for failure in result.failures] == [second.url]
    assert result.failures[0].kind is FailureKind.SESSION_BLOCKED
    assert checkpoints == [(1, False), (2, False), (2, True)]
    assert events[-1].kind is EventKind.FINISHED
    assert events[-1].phase is RunPhase.BLOCKED


def test_runner_finalizes_failed_probe_exception_with_failure_record(
    tmp_path: Path,
) -> None:
    item = InputItem("https://www.kkday.com/zh-tw/product/1-a")
    checkpoints: list[tuple[int, bool]] = []
    events = []

    class ProbeFailureSession(FakeSession):
        def probe_member(self, market: str) -> SessionProbe:
            raise RuntimeError("probe transport failed")

    runner = TaskRunner(
        ProbeFailureSession(),
        lambda _page, _config, _continue: FakeScraper(),
        sleep=lambda _seconds: None,
    )

    result = runner.run(
        [item],
        RunConfig(date(2026, 7, 22), tmp_path),
        RunControl(),
        events.append,
        lambda products, final: checkpoints.append((len(products), final))
        or (tmp_path / "result.xlsx" if final else None),
    )

    assert result.terminal_phase is RunPhase.FAILED
    assert result.requested_count == 1
    assert result.processed_count == 1
    assert result.final_checkpoint_saved is True
    assert result.failures[0].url == item.url
    assert result.failures[0].stage == "member_probe"
    assert checkpoints == [(1, False), (1, True)]
    assert events[-1].kind is EventKind.FINISHED
    assert events[-1].phase is RunPhase.FAILED


def test_first_product_navigation_failure_does_not_use_member_probe_as_recovery(
    tmp_path: Path,
) -> None:
    item = InputItem("https://www.kkday.com/zh-tw/product/1-a")
    session = FakeSession()

    class NavigationFailureScraper:
        def scrape(self, current, _probe, _config):
            return ProductResult(
                current,
                None,
                (),
                (
                    FailureRecord(
                        FailureKind.NAVIGATION,
                        current.url,
                        "snapshot",
                        "timeout",
                        True,
                    ),
                ),
            )

    events = []
    runner = TaskRunner(
        session,
        lambda _page, _config, _continue: NavigationFailureScraper(),
        sleep=lambda _seconds: None,
    )

    result = runner.run(
        [item],
        RunConfig(date(2026, 7, 22), tmp_path),
        RunControl(),
        events.append,
        lambda _products, _final: None,
    )

    assert session.probe_calls == 1
    assert len(result.products) == 1
    assert events[-1].phase is RunPhase.FAILED


def test_runner_enters_running_only_after_first_sku_readiness(
    tmp_path: Path,
) -> None:
    item = InputItem("https://www.kkday.com/zh-tw/product/1-a")
    events = []
    runner = TaskRunner(
        FakeSession(),
        lambda _page, _config, _continue: FakeScraper(),
        sleep=lambda _seconds: None,
    )

    runner.run(
        [item],
        RunConfig(date(2026, 7, 22), tmp_path),
        RunControl(),
        events.append,
        lambda _products, _final: None,
    )

    phases = [event.phase for event in events if event.phase is not None]
    readiness_index = next(
        index
        for index, event in enumerate(events)
        if event.kind is EventKind.READINESS
        and isinstance(event.payload, ReadinessReport)
        and event.payload.sku_api_ready is True
    )
    running_index = next(
        index for index, event in enumerate(events) if event.phase is RunPhase.RUNNING
    )
    assert phases[0] is RunPhase.VERIFYING
    assert readiness_index < running_index


def test_later_generic_navigation_failure_does_not_stop_batch(
    tmp_path: Path,
) -> None:
    items = [
        InputItem("https://www.kkday.com/zh-tw/product/1-a"),
        InputItem("https://www.kkday.com/zh-tw/product/2-b"),
        InputItem("https://www.kkday.com/zh-tw/product/3-c"),
    ]

    class SequenceScraper(FakeScraper):
        def scrape(self, item, probe, config):
            if item is items[1]:
                self.calls.append(item.url)
                return ProductResult(
                    item,
                    None,
                    (),
                    (
                        FailureRecord(
                            FailureKind.NAVIGATION,
                            item.url,
                            "snapshot",
                            "timeout",
                            True,
                        ),
                    ),
                )
            return super().scrape(item, probe, config)

    scraper = SequenceScraper()
    runner = TaskRunner(
        FakeSession(),
        lambda _page, _config, _continue: scraper,
        sleep=lambda _seconds: None,
    )
    events = []

    runner.run(
        items,
        RunConfig(date(2026, 7, 22), tmp_path),
        RunControl(),
        events.append,
        lambda _products, _final: None,
    )

    assert scraper.calls == [item.url for item in items]
    assert events[-1].phase is RunPhase.COMPLETED


def test_stop_before_next_product_is_cooperative(tmp_path: Path) -> None:
    control = RunControl()
    control.stop()
    events = []
    runner = TaskRunner(
        FakeSession(),
        lambda _page, _config, _continue: FakeScraper(),
        sleep=lambda _seconds: None,
    )

    result = runner.run(
        [InputItem("https://www.kkday.com/zh-tw/product/1-a")],
        RunConfig(date(2026, 7, 22), tmp_path),
        control,
        events.append,
        lambda _products, _final: None,
    )

    assert result.products == ()
    assert result.stopped is True
    assert events[-1].phase is RunPhase.STOPPED


def test_checkpoint_failure_emits_failed_terminal_event(tmp_path: Path) -> None:
    item = InputItem("https://www.kkday.com/zh-tw/product/1-a")
    events = []
    runner = TaskRunner(
        FakeSession(),
        lambda _page, _config, _continue: FakeScraper(),
        sleep=lambda _seconds: None,
    )

    def fail_checkpoint(_products, _final):
        raise OSError("disk full")

    result = runner.run(
        [item],
        RunConfig(date(2026, 7, 22), tmp_path),
        RunControl(),
        events.append,
        fail_checkpoint,
    )

    assert result.output_path is None
    assert result.terminal_phase is RunPhase.FAILED
    assert result.final_checkpoint_saved is False
    assert events[-2].kind is EventKind.FAILURE
    assert events[-1].kind is EventKind.FINISHED
    assert events[-1].phase is RunPhase.FAILED


def test_worker_rejects_duplicate_run_without_replacing_active_control(
    tmp_path: Path, monkeypatch
) -> None:
    started = Event()
    release = Event()
    controls: list[RunControl] = []

    class BlockingRunner:
        def __init__(self, _session) -> None:
            pass

        def run(self, _items, _config, control, reporter, _checkpoint):
            controls.append(control)
            started.set()
            release.wait(2)
            now = datetime.now()
            result = RunResult((), None, now, now, control.stopped)
            reporter(
                AppEvent(
                    EventKind.FINISHED,
                    "done",
                    RunPhase.STOPPED if control.stopped else RunPhase.COMPLETED,
                    payload=result,
                )
            )
            return result

    class ClosableSession:
        def close(self) -> None:
            pass

    monkeypatch.setattr("kkday_scraper.task_runner.TaskRunner", BlockingRunner)
    config = RunConfig(date(2026, 7, 22), tmp_path)
    worker = WorkerService(
        lambda _event: None,
        lambda _config: lambda _products, _final: None,
    )
    worker._session = ClosableSession()
    try:
        assert worker.run([], config) is True
        assert started.wait(2)
        active_control = controls[0]

        assert worker.run([], config) is False
        assert worker.control is active_control
        worker.stop()
        assert active_control.stopped is True
    finally:
        release.set()
        worker.shutdown()
        worker._thread.join(2)


def test_worker_keeps_all_session_calls_on_one_background_thread(
    tmp_path: Path,
) -> None:
    ready = Event()
    finished = Event()
    calls: list[tuple[str, int]] = []
    launch_permissions: list[bool] = []

    class ThreadSession:
        def __init__(self, _config: RunConfig) -> None:
            calls.append(("init", get_ident()))

        @property
        def page(self) -> object:
            calls.append(("page", get_ident()))
            return object()

        def connect(self, allow_launch: bool = True) -> None:
            calls.append(("connect", get_ident()))
            launch_permissions.append(allow_launch)

        def probe_member(self, market: str) -> SessionProbe:
            calls.append(("probe", get_ident()))
            return SessionProbe(
                True, True, True, "KRW", market, "https://www.kkday.com"
            )

        def close(self) -> None:
            calls.append(("close", get_ident()))

    def report(event) -> None:
        if event.phase is RunPhase.READY:
            ready.set()
        if event.kind is EventKind.FINISHED:
            finished.set()

    config = RunConfig(date(2026, 7, 22), tmp_path)
    worker = WorkerService(
        report,
        lambda _config: lambda _products, _final: None,
        session_factory=ThreadSession,
    )
    worker.connect(config)
    assert ready.wait(2)
    worker.run([], config)
    assert finished.wait(2)
    worker.shutdown()
    worker._thread.join(2)

    session_thread_ids = {thread_id for _, thread_id in calls}
    assert len(session_thread_ids) == 1
    assert next(iter(session_thread_ids)) != main_thread().ident
    assert [name for name, _ in calls][-1] == "close"
    assert launch_permissions == [False]


def test_worker_bootstrap_allows_public_preflight_without_member_login(
    tmp_path: Path,
) -> None:
    ready = Event()
    endpoint = BrowserEndpoint(
        BrowserKind.EDGE,
        49231,
        "ws://127.0.0.1:49231/devtools/browser/private-session",
        tmp_path / "edge",
        True,
    )

    class FakeBootstrapper:
        def start(self, browser, homepage=None):
            assert browser is BrowserKind.EDGE
            assert homepage == "https://www.kkday.com/zh-hk"
            return endpoint

    class FakeSession:
        page = object()

        def __init__(self, _config):
            self.connect_endpoints = []

        def connect(self, allow_launch=False, endpoint=None):
            assert allow_launch is False
            self.connect_endpoints.append(endpoint)

        def probe_member(self, market):
            ready.set()
            return SessionProbe(
                True,
                True,
                False,
                "KRW",
                market,
                "https://www.kkday.com/zh-tw",
            )

        def close(self):
            pass

    events = []
    config = RunConfig(date(2026, 7, 22), tmp_path, market="zh-hk")
    worker = WorkerService(
        events.append,
        lambda _config: lambda _products, _final: None,
        session_factory=FakeSession,
        bootstrapper_factory=FakeBootstrapper,
    )
    try:
        assert worker.bootstrap_browser(config, BrowserKind.EDGE)
        assert ready.wait(2)
        readiness = next(
            event
            for event in events
            if event.kind is EventKind.READINESS
        )
        assert readiness.phase is RunPhase.READY
        assert "公开商品" in readiness.message
        assert isinstance(
            next(
                event.payload
                for event in events
                if isinstance(event.payload, BrowserConnectionInfo)
            ),
            BrowserConnectionInfo,
        )
        assert all("private-session" not in event.message for event in events)
    finally:
        worker.shutdown()
        worker._thread.join(2)


def test_worker_recheck_after_manual_login_reuses_same_session(
    tmp_path: Path,
) -> None:
    probes = [
        SessionProbe(
            True,
            True,
            False,
            "KRW",
            "zh-tw",
            "https://www.kkday.com/zh-tw",
        ),
        SessionProbe(
            True,
            True,
            True,
            "KRW",
            "zh-tw",
            "https://www.kkday.com/zh-tw",
        ),
    ]
    probe_done = Event()
    first_probe_done = Event()

    class FakeSession:
        page = object()

        def __init__(self, _config):
            self.connect_count = 0
            self.probe_count = 0

        def connect(self, allow_launch=False, endpoint=None):
            self.connect_count += 1

        def probe_member(self, market):
            result = probes[self.probe_count]
            self.probe_count += 1
            if self.probe_count == 1:
                first_probe_done.set()
            if self.probe_count == 2:
                probe_done.set()
            return result

        def close(self):
            pass

    events = []
    config = RunConfig(date(2026, 7, 22), tmp_path)
    worker = WorkerService(
        events.append,
        lambda _config: lambda _products, _final: None,
        session_factory=FakeSession,
    )
    try:
        assert worker.connect_existing(config)
        assert first_probe_done.wait(2)
        assert worker.probe_current_session(config)
        assert probe_done.wait(2)
        session = worker._session
        assert session is not None
        assert session.connect_count == 1
        assert [event.phase for event in events if event.kind is EventKind.READINESS] == [
            RunPhase.READY,
            RunPhase.READY,
        ]
    finally:
        worker.shutdown()
        worker._thread.join(2)


def test_worker_connection_failure_clears_readiness_layers(tmp_path: Path) -> None:
    class FailingSession:
        page = object()

        def __init__(self, _config):
            pass

        def connect(self, allow_launch=False, endpoint=None):
            raise RuntimeError("CDP handshake failed")

        def probe_member(self, market):
            raise AssertionError("probe must not run after connect failure")

        def close(self):
            pass

    events = []
    worker = WorkerService(
        events.append,
        lambda _config: lambda _products, _final: None,
        session_factory=FailingSession,
    )
    try:
        assert worker.connect_existing(RunConfig(date(2026, 7, 22), tmp_path))
        for _ in range(20):
            if any(event.kind is EventKind.FAILURE for event in events):
                break
            Event().wait(0.01)
        readiness = next(
            event for event in events if event.kind is EventKind.READINESS
        )
        assert readiness.payload.browser_connected is False
        assert readiness.payload.member_api_ready is False
        assert readiness.payload.product_page_ready is None
        assert readiness.payload.sku_api_ready is None
    finally:
        worker.shutdown()
        worker._thread.join(2)


def test_stop_before_bootstrap_does_not_poison_next_operation(tmp_path: Path) -> None:
    started = Event()
    endpoint = BrowserEndpoint(
        BrowserKind.EDGE,
        49234,
        "ws://127.0.0.1:49234/devtools/browser/private-session",
        tmp_path / "edge",
        True,
    )

    class FakeBootstrapper:
        def start(self, _browser, _homepage=None):
            started.set()
            return endpoint

    class FakeSession:
        page = object()

        def __init__(self, _config):
            pass

        def connect(self, allow_launch=False, endpoint=None):
            pass

        def probe_member(self, market):
            return SessionProbe(
                True, True, True, "KRW", market, "https://www.kkday.com/zh-tw"
            )

        def close(self):
            pass

    events = []
    worker = WorkerService(
        events.append,
        lambda _config: lambda _products, _final: None,
        session_factory=FakeSession,
        bootstrapper_factory=FakeBootstrapper,
    )
    try:
        worker.stop()
        assert worker.bootstrap_browser(
            RunConfig(date(2026, 7, 22), tmp_path), BrowserKind.EDGE
        )
        assert started.wait(2)
        assert any(event.phase is RunPhase.READY for event in events)
    finally:
        worker.shutdown()
        worker._thread.join(2)


def test_worker_serializes_connection_and_run_operations(tmp_path: Path) -> None:
    started = Event()
    release = Event()

    class BlockingSession:
        page = object()

        def __init__(self, _config):
            pass

        def connect(self, allow_launch=False, endpoint=None):
            started.set()
            release.wait(2)

        def probe_member(self, market):
            return SessionProbe(
                True, True, True, "KRW", market, "https://www.kkday.com/zh-tw"
            )

        def close(self):
            pass

    worker = WorkerService(
        lambda _event: None,
        lambda _config: lambda _products, _final: None,
        session_factory=BlockingSession,
    )
    config = RunConfig(date(2026, 7, 22), tmp_path)
    try:
        assert worker.connect_existing(config)
        assert started.wait(2)
        assert worker.connect_existing(config) is False
        assert worker.run([], config) is False
    finally:
        worker.stop()
        release.set()
        worker.shutdown()
        worker._thread.join(2)
