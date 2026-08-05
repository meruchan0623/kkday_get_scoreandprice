from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from pathlib import Path
from queue import Queue
from random import uniform
from threading import Event, Lock, Thread
from time import sleep
from typing import Callable, Protocol

from .browser_api import BrowserApiClient, SessionBlockedError, SessionExpiredError
from .browser_bootstrap import BrowserBootstrapper
from .browser_session import BrowserSession, browser_connection_info_for_cdp
from .models import (
    AppEvent,
    BrowserConnectionInfo,
    BrowserEndpoint,
    BrowserKind,
    EventKind,
    FailureKind,
    FailureRecord,
    InputItem,
    ProductResult,
    ReadinessReport,
    RunConfig,
    RunPhase,
    RunResult,
    market_homepage,
)
from .product_scraper import ProductScraper


Reporter = Callable[[AppEvent], None]
Checkpoint = Callable[[tuple[ProductResult, ...], bool], object | None]


class SessionLike(Protocol):
    @property
    def page(self) -> object: ...

    def connect(
        self,
        allow_launch: bool = False,
        endpoint: BrowserEndpoint | None = None,
    ) -> None: ...

    def probe_member(self, market: str): ...

    def close(self) -> None: ...


class RunControl:
    def __init__(self) -> None:
        self._running = Event()
        self._running.set()
        self._stopped = Event()

    @property
    def stopped(self) -> bool:
        return self._stopped.is_set()

    def pause(self) -> None:
        self._running.clear()

    def resume(self) -> None:
        self._running.set()

    def stop(self) -> None:
        self._stopped.set()
        self._running.set()

    def wait(self) -> bool:
        while not self._stopped.is_set():
            if self._running.wait(timeout=0.2):
                return True
        return False


class TaskRunner:
    def __init__(
        self,
        session: SessionLike,
        scraper_factory: Callable[
            [object, RunConfig, Callable[[], bool]], ProductScraper
        ]
        | None = None,
        *,
        sleep: Callable[[float], None] = sleep,
        uniform: Callable[[float, float], float] = uniform,
    ) -> None:
        self.session = session
        self.sleep = sleep
        self.uniform = uniform
        self.scraper_factory = scraper_factory or self._default_scraper

    def _default_scraper(
        self,
        page: object,
        config: RunConfig,
        continue_run: Callable[[], bool],
    ) -> ProductScraper:
        api = BrowserApiClient(
            page,
            config.market,
            config.request_timeout_ms,
        )
        return ProductScraper(page, api, continue_run=continue_run)

    def run(
        self,
        items: list[InputItem],
        config: RunConfig,
        control: RunControl,
        reporter: Reporter,
        checkpoint: Checkpoint,
    ) -> RunResult:
        started = datetime.now()
        products: list[ProductResult] = []
        blocked = False
        blocked_reason: str | None = None
        preflight_failed = False
        preflight_verified = False
        checkpoint_error: Exception | None = None
        output_path: Path | None = None
        current_index = -1
        latest_readiness: ReadinessReport | None = None
        reporter(
            AppEvent(
                EventKind.PHASE,
                "正在验证首个商品" if items else "开始抓取",
                RunPhase.VERIFYING if items else RunPhase.RUNNING,
                0,
                len(items),
            )
        )

        def publish_readiness(report: ReadinessReport) -> None:
            nonlocal latest_readiness, preflight_verified
            latest_readiness = report
            reporter(
                AppEvent(
                    EventKind.READINESS,
                    report.reason or "抓取可用性状态已更新",
                    payload=report,
                )
            )
            if (
                current_index == 0
                and report.business_ready
                and not preflight_verified
            ):
                preflight_verified = True
                reporter(
                    AppEvent(
                        EventKind.PHASE,
                        "首个商品验证通过，开始批次抓取",
                        RunPhase.RUNNING,
                        1,
                        len(items),
                    )
                )

        scraper = self.scraper_factory(self.session.page, config, control.wait)
        if hasattr(scraper, "readiness_reporter"):
            scraper.readiness_reporter = publish_readiness

        for index, item in enumerate(items):
            current_index = index
            if control.stopped or not control.wait():
                break
            reporter(
                AppEvent(
                    EventKind.PROGRESS,
                    f"处理 {item.url}",
                    RunPhase.VERIFYING
                    if index == 0 and not preflight_verified
                    else RunPhase.RUNNING,
                    index + 1,
                    len(items),
                )
            )
            probe = self.session.probe_member(config.market)
            publish_readiness(
                replace(
                    ReadinessReport.from_member_probe(probe),
                    product_url=item.url,
                )
            )
            if not probe.member_api_ready:
                blocked = True
                reporter(
                    AppEvent(
                        EventKind.FAILURE,
                        probe.block_reason or "浏览器会话不可用",
                        RunPhase.BLOCKED,
                        index + 1,
                        len(items),
                    )
                )
                break
            try:
                product = scraper.scrape(item, probe, config)
            except (SessionBlockedError, SessionExpiredError) as exc:
                blocked = True
                blocked_reason = str(exc)
                product = ProductResult(
                    item,
                    None,
                    (),
                    (
                        FailureRecord(
                            FailureKind.SESSION_EXPIRED
                            if isinstance(exc, SessionExpiredError)
                            else FailureKind.SESSION_BLOCKED,
                            item.url,
                            "product",
                            str(exc),
                            False,
                            item.input_order,
                        ),
                    ),
                )
                reporter(
                    AppEvent(
                        EventKind.FAILURE,
                        str(exc),
                        RunPhase.BLOCKED,
                        index + 1,
                        len(items),
                    )
                )
            except Exception as exc:
                product = ProductResult(
                    item,
                    None,
                    (),
                    (
                        FailureRecord(
                            FailureKind.API,
                            item.url,
                            "product",
                            str(exc),
                            True,
                            item.input_order,
                        ),
                    ),
                )

            products.append(product)
            try:
                checkpoint_output = checkpoint(tuple(products), False)
                if isinstance(checkpoint_output, Path):
                    output_path = checkpoint_output
            except Exception as exc:
                checkpoint_error = exc
                reporter(
                    AppEvent(
                        EventKind.FAILURE,
                        f"保存检查点失败：{exc}",
                        RunPhase.FAILED,
                        index + 1,
                        len(items),
                    )
                )
                break
            reporter(
                AppEvent(
                    EventKind.PRODUCT_RESULT,
                    f"商品完成：{item.url}",
                    RunPhase.BLOCKED if blocked else RunPhase.RUNNING,
                    index + 1,
                    len(items),
                    product,
                )
            )
            if blocked:
                break
            if index == 0 and not preflight_verified and not control.stopped:
                preflight_failed = True
                reason = (
                    latest_readiness.reason
                    if latest_readiness is not None and latest_readiness.reason
                    else "首个商品未通过商品页与 SKU 接口验证"
                )
                reporter(
                    AppEvent(
                        EventKind.FAILURE,
                        reason,
                        RunPhase.FAILED,
                        index + 1,
                        len(items),
                    )
                )
                break
            if index + 1 < len(items) and not control.stopped:
                self.sleep(self.uniform(*config.product_delay_range))

        if checkpoint_error is None:
            try:
                final_output = checkpoint(tuple(products), True)
                if isinstance(final_output, Path):
                    output_path = final_output
            except Exception as exc:
                checkpoint_error = exc
                reporter(
                    AppEvent(
                        EventKind.FAILURE,
                        f"保存最终结果失败：{exc}",
                        RunPhase.FAILED,
                        len(products),
                        len(items),
                    )
                )

        if checkpoint_error is not None:
            phase = RunPhase.FAILED
            message = "任务保存失败"
        elif control.stopped:
            phase = RunPhase.STOPPED
            message = "任务已停止"
        elif blocked:
            phase = RunPhase.BLOCKED
            message = blocked_reason or "任务因浏览器会话不可用而停止"
        elif preflight_failed:
            phase = RunPhase.FAILED
            message = "首个商品验证失败"
        else:
            phase = RunPhase.COMPLETED
            message = "任务完成"
        result = RunResult(
            products=tuple(products),
            output_path=output_path,
            started_at=started,
            finished_at=datetime.now(),
            stopped=control.stopped,
        )
        reporter(
            AppEvent(
                EventKind.FINISHED,
                message,
                phase,
                len(products),
                len(items),
                result,
            )
        )
        return result


class WorkerCommandKind(str, Enum):
    BOOTSTRAP = "bootstrap"
    CONNECT = "connect"
    PROBE = "probe"
    RUN = "run"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True)
class WorkerCommand:
    kind: WorkerCommandKind
    config: RunConfig | None = None
    items: tuple[InputItem, ...] = ()
    control: RunControl | None = None
    browser_kind: BrowserKind = BrowserKind.AUTO
    operation_control: RunControl | None = None


class WorkerService:
    def __init__(
        self,
        reporter: Reporter,
        checkpoint_factory: Callable[[RunConfig], Checkpoint],
        session_factory: Callable[[RunConfig], SessionLike] = BrowserSession,
        bootstrapper_factory: Callable[[], BrowserBootstrapper] = BrowserBootstrapper,
    ) -> None:
        self.reporter = reporter
        self.checkpoint_factory = checkpoint_factory
        self.session_factory = session_factory
        self.bootstrapper_factory = bootstrapper_factory
        self.commands: Queue[WorkerCommand] = Queue()
        self.control = RunControl()
        self._state_lock = Lock()
        self._run_active = False
        self._shutdown_requested = False
        self._session: SessionLike | None = None
        self._operation_control: RunControl | None = None
        self._thread = Thread(
            target=self._loop,
            name="kkday-browser-worker",
            daemon=True,
        )
        self._thread.start()

    def connect(self, config: RunConfig) -> bool:
        return self.connect_existing(config)

    def connect_existing(self, config: RunConfig) -> bool:
        with self._state_lock:
            accepted = (
                not self._shutdown_requested
                and not self._run_active
                and self._operation_control is None
            )
            operation_control = RunControl() if accepted else None
            if operation_control is not None:
                self._operation_control = operation_control
        if not accepted:
            self.reporter(AppEvent(EventKind.LOG, "当前任务尚未结束，无法重新连接"))
            return False
        self.commands.put(
            WorkerCommand(
                WorkerCommandKind.CONNECT,
                config,
                operation_control=operation_control,
            )
        )
        return True

    def bootstrap_browser(
        self, config: RunConfig, browser: BrowserKind = BrowserKind.AUTO
    ) -> bool:
        with self._state_lock:
            accepted = (
                not self._shutdown_requested
                and not self._run_active
                and self._operation_control is None
            )
            operation_control = RunControl() if accepted else None
            if operation_control is not None:
                self._operation_control = operation_control
        if not accepted:
            self.reporter(AppEvent(EventKind.LOG, "当前任务尚未结束，无法启动浏览器"))
            return False
        self.commands.put(
            WorkerCommand(
                WorkerCommandKind.BOOTSTRAP,
                config,
                browser_kind=browser,
                operation_control=operation_control,
            )
        )
        return True

    def probe_current_session(self, config: RunConfig) -> bool:
        with self._state_lock:
            accepted = (
                not self._shutdown_requested
                and not self._run_active
                and self._operation_control is None
            )
            operation_control = RunControl() if accepted else None
            if operation_control is not None:
                self._operation_control = operation_control
        if not accepted:
            self.reporter(AppEvent(EventKind.LOG, "当前任务尚未结束，无法重新检测"))
            return False
        self.commands.put(
            WorkerCommand(
                WorkerCommandKind.PROBE,
                config,
                operation_control=operation_control,
            )
        )
        return True

    def run(self, items: list[InputItem], config: RunConfig) -> bool:
        with self._state_lock:
            if (
                self._shutdown_requested
                or self._run_active
                or self._operation_control is not None
            ):
                accepted = False
            else:
                accepted = True
                self._run_active = True
                self.control = RunControl()
                self._operation_control = None
                control = self.control
        if not accepted:
            self.reporter(AppEvent(EventKind.LOG, "已有任务正在排队或运行"))
            return False
        self.commands.put(
            WorkerCommand(
                WorkerCommandKind.RUN,
                config,
                tuple(items),
                control,
            )
        )
        return True

    def pause(self) -> None:
        self.control.pause()
        self.reporter(AppEvent(EventKind.PHASE, "已暂停", RunPhase.PAUSED))

    def resume(self) -> None:
        self.control.resume()
        self.reporter(AppEvent(EventKind.PHASE, "继续运行", RunPhase.RUNNING))

    def stop(self) -> None:
        self.control.stop()
        with self._state_lock:
            if self._operation_control is not None:
                self._operation_control.stop()
        self.reporter(AppEvent(EventKind.PHASE, "正在停止", RunPhase.STOPPING))

    def shutdown(self) -> None:
        with self._state_lock:
            if self._shutdown_requested:
                return
            self._shutdown_requested = True
            self.control.stop()
            if self._operation_control is not None:
                self._operation_control.stop()
        self.commands.put(WorkerCommand(WorkerCommandKind.SHUTDOWN))

    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def _loop(self) -> None:
        while True:
            command = self.commands.get()
            if command.kind is WorkerCommandKind.SHUTDOWN:
                if self._session is not None:
                    self._session.close()
                    self._session = None
                return
            with self._state_lock:
                shutting_down = self._shutdown_requested
            if shutting_down and command.kind in {
                WorkerCommandKind.CONNECT,
                WorkerCommandKind.BOOTSTRAP,
                WorkerCommandKind.PROBE,
            }:
                continue
            if command.config is None:
                continue

            if command.kind is WorkerCommandKind.CONNECT:
                self._connect(command.config, command.operation_control)
            elif command.kind is WorkerCommandKind.BOOTSTRAP:
                self._bootstrap(
                    command.config,
                    command.browser_kind,
                    command.operation_control,
                )
            elif command.kind is WorkerCommandKind.PROBE:
                self._probe(command.config, command.operation_control)
            elif command.kind is WorkerCommandKind.RUN:
                self._run(command)

    def _clear_operation(self, operation_control: RunControl | None) -> None:
        with self._state_lock:
            if self._operation_control is operation_control:
                self._operation_control = None

    def _connection_failure(
        self, message: str, *, browser_connected: bool = False
    ) -> None:
        readiness = ReadinessReport(
            browser_connected=browser_connected,
            member_api_ready=False,
            product_page_ready=None,
            price_calendar_ready=None,
            sku_api_ready=None,
            product_url=None,
            reason=message,
        )
        self.reporter(
            AppEvent(EventKind.READINESS, message, RunPhase.FAILED, payload=readiness)
        )
        self.reporter(AppEvent(EventKind.FAILURE, message, RunPhase.FAILED))

    def _connection_stopped(self, message: str) -> None:
        self.reporter(
            AppEvent(
                EventKind.READINESS,
                message,
                RunPhase.STOPPED,
                payload=ReadinessReport(
                    browser_connected=False,
                    member_api_ready=False,
                    product_page_ready=None,
                    price_calendar_ready=None,
                    sku_api_ready=None,
                    product_url=None,
                    reason=message,
                ),
            )
        )
        self.reporter(AppEvent(EventKind.PHASE, message, RunPhase.STOPPED))

    def _connect(
        self, config: RunConfig, operation_control: RunControl | None
    ) -> None:
        try:
            if operation_control is not None and operation_control.stopped:
                self._connection_stopped("连接已停止")
                return
            self.reporter(
                AppEvent(EventKind.PHASE, "正在连接浏览器", RunPhase.CONNECTING)
            )
            if self._session is not None:
                self._session.close()
                self._session = None
            self._session = self.session_factory(config)
            self._session.connect(allow_launch=False)
            connection_info = browser_connection_info_for_cdp(config.cdp_url)
            if connection_info is not None:
                self.reporter(
                    AppEvent(
                        EventKind.PHASE,
                        f"已连接 {connection_info.browser.value.title()} 现有 CDP",
                        RunPhase.CONNECTING,
                        payload=connection_info,
                    )
                )
            if operation_control is not None and operation_control.stopped:
                self._session.close()
                self._session = None
                self._connection_stopped("连接已停止")
                return
            probe = self._session.probe_member(config.market)
            if operation_control is not None and operation_control.stopped:
                self._session.close()
                self._session = None
                self._connection_stopped("登录态检测已停止")
                return
            if probe.member_api_ready and probe.is_login:
                phase = RunPhase.READY
                message = "浏览器已连接，登录态可用，商品待验证"
            elif probe.member_api_ready:
                phase = RunPhase.READY
                message = "浏览器已连接，会员未登录；可继续验证公开商品接口"
            else:
                phase = RunPhase.BLOCKED
                message = probe.block_reason or "会话不可用"
            readiness = ReadinessReport.from_member_probe(probe)
            self.reporter(
                AppEvent(
                    EventKind.READINESS,
                    message,
                    phase,
                    payload=readiness,
                )
            )
        except Exception as exc:
            if self._session is not None:
                self._session.close()
                self._session = None
            if operation_control is not None and operation_control.stopped:
                self._connection_stopped("连接已停止")
            else:
                self._connection_failure(f"浏览器连接失败：{exc}")
        finally:
            self._clear_operation(operation_control)

    def _probe(
        self, config: RunConfig, operation_control: RunControl | None
    ) -> None:
        try:
            if operation_control is not None and operation_control.stopped:
                self.reporter(
                    AppEvent(EventKind.PHASE, "重新检测已停止", RunPhase.STOPPED)
                )
                return
            if self._session is None:
                self._connection_failure("当前没有可重新检测的浏览器会话")
                return
            self.reporter(
                AppEvent(EventKind.PHASE, "正在重新检测 KKday 登录态", RunPhase.CONNECTING)
            )
            probe = self._session.probe_member(config.market)
            if operation_control is not None and operation_control.stopped:
                self.reporter(
                    AppEvent(EventKind.PHASE, "重新检测已停止", RunPhase.STOPPED)
                )
                return
            if probe.member_api_ready and probe.is_login:
                phase = RunPhase.READY
                message = "登录态可用，商品待验证"
            elif probe.member_api_ready:
                phase = RunPhase.READY
                message = "会员未登录；可继续验证公开商品接口"
            else:
                phase = RunPhase.BLOCKED
                message = probe.block_reason or "KKday 登录态检测失败"
            self.reporter(
                AppEvent(
                    EventKind.READINESS,
                    message,
                    phase,
                    payload=ReadinessReport.from_member_probe(probe),
                )
            )
        except Exception as exc:
            if operation_control is not None and operation_control.stopped:
                self.reporter(
                    AppEvent(EventKind.PHASE, "重新检测已停止", RunPhase.STOPPED)
                )
            else:
                self._connection_failure(
                    f"重新检测登录态失败：{exc}", browser_connected=True
                )
        finally:
            self._clear_operation(operation_control)

    def _bootstrap(
        self,
        config: RunConfig,
        browser_kind: BrowserKind,
        operation_control: RunControl | None,
    ) -> None:
        try:
            if operation_control is not None and operation_control.stopped:
                self._connection_stopped("浏览器启动已停止")
                return
            self.reporter(
                AppEvent(EventKind.PHASE, "正在启动 KKday 调试浏览器", RunPhase.BOOTSTRAPPING)
            )
            bootstrapper = self.bootstrapper_factory()
            if isinstance(bootstrapper, BrowserBootstrapper):
                bootstrapper.cancelled = lambda: (
                    operation_control is not None and operation_control.stopped
                )
            endpoint = bootstrapper.start(
                browser_kind, market_homepage(config.market)
            )
            if operation_control is not None and operation_control.stopped:
                self._connection_stopped("浏览器启动已停止")
                return
            self.reporter(
                AppEvent(
                    EventKind.PHASE,
                    f"发现 {endpoint.browser.value.title()} 调试 Profile（端口 {endpoint.port}），正在连接",
                    RunPhase.CONNECTING,
                    payload=BrowserConnectionInfo(
                        browser=endpoint.browser,
                        port=endpoint.port,
                        profile_dir=endpoint.profile_dir,
                        owns_process=endpoint.owns_process,
                    ),
                )
            )
            if self._session is not None:
                self._session.close()
            self._session = self.session_factory(config)
            self._session.connect(allow_launch=False, endpoint=endpoint)
            if operation_control is not None and operation_control.stopped:
                self._session.close()
                self._session = None
                self._connection_stopped("浏览器连接已停止")
                return
            probe = self._session.probe_member(config.market)
            if operation_control is not None and operation_control.stopped:
                self._session.close()
                self._session = None
                self._connection_stopped("登录态检测已停止")
                return
            if probe.member_api_ready and probe.is_login:
                phase = RunPhase.READY
                message = "调试浏览器已连接，登录态可用，商品待验证"
            elif probe.member_api_ready:
                phase = RunPhase.READY
                message = "调试浏览器已连接，会员未登录；可继续验证公开商品接口"
            else:
                phase = RunPhase.BLOCKED
                message = probe.block_reason or "KKday 登录态检测失败"
            self.reporter(
                AppEvent(
                    EventKind.READINESS,
                    message,
                    phase,
                    payload=ReadinessReport.from_member_probe(probe),
                )
            )
        except Exception as exc:
            if self._session is not None:
                self._session.close()
                self._session = None
            if operation_control is not None and operation_control.stopped:
                self._connection_stopped("浏览器启动已停止")
            else:
                self._connection_failure(f"一键启动调试浏览器失败：{exc}")
        finally:
            self._clear_operation(operation_control)

    def _run(self, command: WorkerCommand) -> None:
        if command.config is None:
            return
        if self._session is None:
            with self._state_lock:
                self._run_active = False
            self._connection_failure("请先连接浏览器")
            return
        control = command.control
        if control is None:
            with self._state_lock:
                self._run_active = False
            self.reporter(
                AppEvent(EventKind.FAILURE, "任务缺少运行控制器", RunPhase.FAILED)
            )
            return
        try:
            runner = TaskRunner(self._session)
            runner.run(
                list(command.items),
                command.config,
                control,
                self.reporter,
                self.checkpoint_factory(command.config),
            )
        except Exception as exc:
            self.reporter(
                AppEvent(
                    EventKind.FAILURE,
                    f"任务运行失败：{exc}",
                    RunPhase.FAILED,
                )
            )
        finally:
            with self._state_lock:
                self._run_active = False
