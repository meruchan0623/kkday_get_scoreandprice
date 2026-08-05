from __future__ import annotations

import platform
import queue
import subprocess
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .exporter import RunExporter
from .gui_state import (
    button_policy,
    readiness_labels,
    session_allows_product_preflight,
)
from .inputs import deduplicate_inputs, load_manual_urls, load_txt, load_vendor_excel
from .models import (
    AppEvent,
    BrowserConnectionInfo,
    BrowserKind,
    EventKind,
    InputItem,
    ProductResult,
    RunConfig,
    RunPhase,
    RunResult,
    ReadinessReport,
    SUPPORTED_MARKETS,
)
from .task_runner import WorkerService


class KKdayScraperApp:
    """Tk shell that delegates every browser operation to one worker thread."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("KKday SKU 价格抓取工具 2.0")
        self.root.geometry("1120x780")
        self.root.minsize(940, 680)

        self.phase = RunPhase.IDLE
        self.session_ready = False
        self.inputs: list[InputItem] = []
        self.last_result: RunResult | None = None
        self.last_output: Path | None = None
        self._closing = False
        self.events: queue.Queue[AppEvent] = queue.Queue()
        self.worker = WorkerService(self.events.put, self._checkpoint_factory)

        self.date_var = tk.StringVar(value=date.today().isoformat())
        self.market_var = tk.StringVar(value="zh-tw")
        self.port_var = tk.StringVar(value="9222")
        self.output_var = tk.StringVar(
            value=str(Path.home() / "Downloads" / "KKday_scraping")
        )
        self.browser_var = tk.StringVar(value="未连接")
        self.browser_name_var = tk.StringVar(value="自动")
        self.browser_profile_var = tk.StringVar(value="未启动")
        self.member_var = tk.StringVar(value="待检测")
        self.product_var = tk.StringVar(value="待商品验证")
        self.sku_var = tk.StringVar(value="待商品验证")
        self.currency_var = tk.StringVar(value="—")
        self.progress_var = tk.StringVar(value="0 / 0")
        self.status_var = tk.StringVar(value="就绪")
        self.pause_text = tk.StringVar(value="暂停")

        self._build()
        self._apply_policy()
        self.root.after(100, self._poll_events)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        session = ttk.LabelFrame(outer, text="浏览器会话", padding=10)
        session.pack(fill=tk.X)
        ttk.Label(session, text="浏览器").grid(row=0, column=0, sticky="w")
        self.browser_combo = ttk.Combobox(
            session,
            textvariable=self.browser_name_var,
            values=("自动", "Edge", "Chrome"),
            state="readonly",
            width=9,
        )
        self.browser_combo.grid(row=0, column=1, padx=(6, 14))
        ttk.Label(session, text="现有 CDP 端口").grid(
            row=0, column=2, sticky="w"
        )
        self.port_entry = ttk.Entry(session, textvariable=self.port_var, width=9)
        self.port_entry.grid(row=0, column=3, padx=(6, 14))
        ttk.Label(session, text="市场").grid(row=0, column=4, sticky="w")
        self.market_combo = ttk.Combobox(
            session,
            textvariable=self.market_var,
            values=SUPPORTED_MARKETS,
            state="readonly",
            width=9,
        )
        self.market_combo.grid(row=0, column=5, padx=(6, 14))
        self.connect_button = ttk.Button(
            session, text="连接现有浏览器", command=self._connect
        )
        self.connect_button.grid(row=0, column=6, padx=(0, 6))
        self.bootstrap_button = ttk.Button(
            session,
            text="一键启动调试浏览器",
            command=self._bootstrap_browser,
        )
        self.bootstrap_button.grid(row=0, column=7, padx=(0, 6))
        self.recheck_button = ttk.Button(
            session,
            text="重新检测登录态",
            command=self._recheck_session,
        )
        self.recheck_button.grid(row=0, column=8, padx=(0, 10))
        ttk.Label(session, text="币种：").grid(row=0, column=9, padx=(4, 0))
        ttk.Label(session, textvariable=self.currency_var).grid(
            row=0, column=10, sticky="w"
        )
        ttk.Label(session, text="连接状态：").grid(
            row=1, column=0, pady=(8, 0)
        )
        ttk.Label(session, textvariable=self.browser_var).grid(
            row=1, column=1, sticky="w", pady=(8, 0)
        )
        ttk.Label(session, text="浏览器：").grid(row=1, column=2, pady=(8, 0))
        ttk.Label(session, textvariable=self.browser_name_var).grid(
            row=1, column=3, sticky="w", pady=(8, 0)
        )
        ttk.Label(session, text="登录态：").grid(row=1, column=4, pady=(8, 0))
        ttk.Label(session, textvariable=self.member_var).grid(
            row=1, column=5, sticky="w", pady=(8, 0)
        )
        ttk.Label(session, text="商品页：").grid(row=1, column=6, pady=(8, 0))
        ttk.Label(session, textvariable=self.product_var).grid(
            row=1, column=7, sticky="w", pady=(8, 0)
        )
        ttk.Label(session, text="SKU 接口：").grid(
            row=1, column=8, padx=(4, 0), pady=(8, 0)
        )
        ttk.Label(session, textvariable=self.sku_var).grid(
            row=1, column=9, sticky="w", pady=(8, 0)
        )
        ttk.Label(session, text="Profile：").grid(
            row=2, column=0, pady=(8, 0)
        )
        ttk.Label(session, textvariable=self.browser_profile_var).grid(
            row=2, column=1, columnspan=4, sticky="w", pady=(8, 0)
        )

        input_frame = ttk.LabelFrame(outer, text="任务输入", padding=10)
        input_frame.pack(fill=tk.X, pady=(10, 0))
        input_frame.columnconfigure(0, weight=1)
        self.manual_text = tk.Text(input_frame, height=3, wrap=tk.NONE)
        self.manual_text.grid(row=0, column=0, columnspan=7, sticky="ew")
        self.add_button = ttk.Button(
            input_frame, text="添加 URL", command=self._add_manual
        )
        self.add_button.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.txt_button = ttk.Button(
            input_frame, text="导入 TXT", command=self._import_txt
        )
        self.txt_button.grid(row=1, column=1, padx=6, pady=(8, 0))
        self.excel_button = ttk.Button(
            input_frame, text="导入 Excel", command=self._import_excel
        )
        self.excel_button.grid(row=1, column=2, padx=6, pady=(8, 0))
        self.remove_button = ttk.Button(
            input_frame, text="移除选中", command=self._remove_selected
        )
        self.remove_button.grid(row=1, column=3, padx=6, pady=(8, 0))
        self.clear_button = ttk.Button(
            input_frame, text="清空", command=self._clear_inputs
        )
        self.clear_button.grid(row=1, column=4, padx=6, pady=(8, 0))
        ttk.Label(input_frame, text="使用日期").grid(
            row=1, column=5, padx=(20, 6), pady=(8, 0)
        )
        self.date_entry = ttk.Entry(
            input_frame, textvariable=self.date_var, width=12
        )
        self.date_entry.grid(row=1, column=6, pady=(8, 0))

        self.input_tree = ttk.Treeview(
            input_frame,
            columns=("vendor", "url", "source"),
            show="headings",
            height=7,
        )
        self.input_tree.heading("vendor", text="厂商")
        self.input_tree.heading("url", text="商品 URL")
        self.input_tree.heading("source", text="来源")
        self.input_tree.column("vendor", width=130, stretch=False)
        self.input_tree.column("url", width=650)
        self.input_tree.column("source", width=160, stretch=False)
        self.input_tree.grid(
            row=2, column=0, columnspan=7, sticky="nsew", pady=(8, 0)
        )

        controls = ttk.Frame(outer)
        controls.pack(fill=tk.X, pady=10)
        ttk.Label(controls, text="输出目录").pack(side=tk.LEFT)
        self.output_entry = ttk.Entry(controls, textvariable=self.output_var)
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.output_button = ttk.Button(
            controls, text="选择", command=self._choose_output
        )
        self.output_button.pack(side=tk.LEFT)
        self.start_button = ttk.Button(controls, text="开始", command=self._start)
        self.start_button.pack(side=tk.LEFT, padx=(14, 4))
        self.pause_button = ttk.Button(
            controls, textvariable=self.pause_text, command=self._toggle_pause
        )
        self.pause_button.pack(side=tk.LEFT, padx=4)
        self.stop_button = ttk.Button(controls, text="停止", command=self._stop)
        self.stop_button.pack(side=tk.LEFT, padx=4)
        self.open_button = ttk.Button(
            controls, text="打开输出", command=self._open_output
        )
        self.open_button.pack(side=tk.LEFT, padx=(4, 0))

        body = ttk.Panedwindow(outer, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)
        result_frame = ttk.LabelFrame(body, text="商品结果", padding=8)
        log_frame = ttk.LabelFrame(body, text="运行日志", padding=8)
        body.add(result_frame, weight=2)
        body.add(log_frame, weight=3)

        self.result_tree = ttk.Treeview(
            result_frame,
            columns=("product", "available", "trusted", "failures"),
            show="headings",
        )
        self.result_tree.heading("product", text="商品")
        self.result_tree.heading("available", text="可售 SKU")
        self.result_tree.heading("trusted", text="可信价格")
        self.result_tree.heading("failures", text="失败")
        self.result_tree.column("product", width=280)
        self.result_tree.column("available", width=80, anchor="center")
        self.result_tree.column("trusted", width=80, anchor="center")
        self.result_tree.column("failures", width=60, anchor="center")
        self.result_tree.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, state=tk.DISABLED
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        status = ttk.Frame(outer)
        status.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(
            status, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w"
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(
            status,
            textvariable=self.progress_var,
            relief=tk.SUNKEN,
            width=12,
            anchor="center",
        ).pack(side=tk.RIGHT)

    def _config(self) -> RunConfig:
        try:
            usage_date = date.fromisoformat(self.date_var.get().strip())
            port = int(self.port_var.get().strip())
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError as exc:
            raise ValueError(
                "日期必须是 YYYY-MM-DD，CDP 端口必须是 1–65535 的整数"
            ) from exc

        output_text = self.output_var.get().strip()
        if not output_text:
            raise ValueError("输出目录不能为空")
        output = Path(output_text).expanduser()
        return RunConfig(
            usage_date=usage_date,
            output_dir=output,
            market=self.market_var.get(),
            cdp_url=f"http://127.0.0.1:{port}",
        )

    def _checkpoint_factory(self, config: RunConfig):
        return RunExporter(config).checkpoint

    def _session_config(self) -> RunConfig:
        return RunConfig(
            usage_date=date.today(),
            output_dir=Path.home() / "Downloads" / "KKday_scraping",
            market=self.market_var.get(),
        )

    def _connect(self) -> None:
        try:
            config = self._config()
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return
        if self.worker.connect_existing(config):
            self.phase = RunPhase.CONNECTING
            self.status_var.set("正在连接现有浏览器…")
            self._apply_policy()

    def _selected_browser_kind(self) -> BrowserKind:
        return {
            "Edge": BrowserKind.EDGE,
            "Chrome": BrowserKind.CHROME,
        }.get(self.browser_combo.get(), BrowserKind.AUTO)

    def _bootstrap_browser(self) -> None:
        try:
            config = self._session_config()
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return
        if self.worker.bootstrap_browser(config, self._selected_browser_kind()):
            self.phase = RunPhase.BOOTSTRAPPING
            self.status_var.set("正在启动 KKday 调试浏览器…")
            self._apply_policy()

    def _recheck_session(self) -> None:
        try:
            config = self._session_config()
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return
        if self.worker.probe_current_session(config):
            self.phase = RunPhase.CONNECTING
            self.status_var.set("正在重新检测 KKday 登录态…")
            self._apply_policy()

    def _add_manual(self) -> None:
        try:
            self.inputs.extend(
                load_manual_urls(self.manual_text.get("1.0", tk.END), len(self.inputs))
            )
            self.inputs = deduplicate_inputs(self.inputs)
            self.manual_text.delete("1.0", tk.END)
            self._refresh_inputs()
        except ValueError as exc:
            messagebox.showerror("URL 错误", str(exc))

    def _import_txt(self) -> None:
        filename = filedialog.askopenfilename(
            filetypes=[("文本文件", "*.txt"), ("全部文件", "*")]
        )
        if not filename:
            return
        try:
            self.inputs.extend(load_txt(Path(filename), len(self.inputs)))
            self.inputs = deduplicate_inputs(self.inputs)
            self._refresh_inputs()
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc))

    def _import_excel(self) -> None:
        filename = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx")])
        if not filename:
            return
        try:
            items, warnings = load_vendor_excel(Path(filename), len(self.inputs))
            self.inputs.extend(items)
            self.inputs = deduplicate_inputs(self.inputs)
            self._refresh_inputs()
            for warning in warnings:
                self._log(warning)
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc))

    def _remove_selected(self) -> None:
        selected = {int(value) for value in self.input_tree.selection()}
        self.inputs = [
            item for index, item in enumerate(self.inputs) if index not in selected
        ]
        self._refresh_inputs()

    def _clear_inputs(self) -> None:
        self.inputs.clear()
        self._refresh_inputs()

    def _refresh_inputs(self) -> None:
        self.input_tree.delete(*self.input_tree.get_children())
        for index, item in enumerate(self.inputs):
            source = str(item.source_path) if item.source_path else "手动"
            self.input_tree.insert(
                "", tk.END, iid=str(index), values=(item.vendor, item.url, source)
            )
        self._apply_policy()

    def _choose_output(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_var.get())
        if selected:
            self.output_var.set(selected)

    def _start(self) -> None:
        if not self.inputs:
            messagebox.showwarning("没有任务", "请先添加 KKday 商品 URL")
            return
        try:
            config = self._config()
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return
        if self.worker.run(self.inputs, config):
            self.result_tree.delete(*self.result_tree.get_children())
            self.last_result = None
            self.last_output = None
            self.phase = RunPhase.VERIFYING
            self.status_var.set("任务已排队，正在验证首个商品")
            self._apply_policy()

    def _toggle_pause(self) -> None:
        if self.phase is RunPhase.RUNNING:
            self.worker.pause()
            self.phase = RunPhase.PAUSED
        elif self.phase is RunPhase.PAUSED:
            self.worker.resume()
            self.phase = RunPhase.RUNNING
        self._apply_policy()

    def _stop(self) -> None:
        self.worker.stop()
        self.phase = RunPhase.STOPPING
        self._apply_policy()

    def _poll_events(self) -> None:
        try:
            while True:
                self._handle_event(self.events.get_nowait())
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _handle_event(self, event: AppEvent) -> None:
        if event.phase is not None:
            self.phase = event.phase
        if event.message:
            self._log(event.message)
            self.status_var.set(event.message)
        if event.current is not None and event.total is not None:
            self.progress_var.set(f"{event.current} / {event.total}")

        if isinstance(event.payload, ReadinessReport):
            labels = readiness_labels(event.payload)
            self.session_ready = session_allows_product_preflight(event.payload)
            self.browser_var.set(labels.browser)
            if self.browser_name_var.get() == "自动" and labels.browser == "已连接":
                self.browser_name_var.set("现有 CDP")
            self.member_var.set(labels.member)
            self.product_var.set(labels.product)
            self.sku_var.set(labels.sku)
            self.currency_var.set(event.payload.currency or "—")
        elif isinstance(event.payload, BrowserConnectionInfo):
            self.browser_name_var.set(event.payload.browser.value.title())
            self.port_var.set(str(event.payload.port))
            self.browser_profile_var.set(
                "已启动专用 Profile"
                if event.payload.owns_process
                else "复用专用 Profile"
            )
        elif (
            event.kind is EventKind.PRODUCT_RESULT
            and isinstance(event.payload, ProductResult)
        ):
            product = event.payload
            name = (
                product.snapshot.name
                if product.snapshot is not None
                else product.input_item.url
            )
            available = sum(row.available for row in product.rows)
            self.result_tree.insert(
                "",
                tk.END,
                values=(
                    name,
                    available,
                    len(product.trusted_rows),
                    len(product.failures),
                ),
            )
        elif event.kind is EventKind.FINISHED and isinstance(
            event.payload, RunResult
        ):
            self.last_result = event.payload
            self.last_output = event.payload.output_path
            if self.last_output is not None:
                self._log(f"输出：{self.last_output}")
        elif event.kind is EventKind.FAILURE:
            if event.message.startswith("浏览器连接失败"):
                self.browser_var.set("未连接")
                self.member_var.set("异常")
            elif event.message.startswith("一键启动调试浏览器失败"):
                self.browser_var.set("未连接")
                self.member_var.set("待检测")
                self.browser_profile_var.set("未启动")
            elif event.message.startswith("重新检测登录态失败"):
                self.member_var.set("异常")

        self.pause_text.set("继续" if self.phase is RunPhase.PAUSED else "暂停")
        self._apply_policy()

    def _log(self, message: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _apply_policy(self) -> None:
        policy = button_policy(
            self.phase,
            bool(self.inputs),
            self.last_result is not None,
            self.session_ready,
        )
        self.connect_button.configure(
            state=tk.NORMAL if policy.connect else tk.DISABLED
        )
        self.bootstrap_button.configure(
            state=tk.NORMAL if policy.bootstrap else tk.DISABLED
        )
        self.recheck_button.configure(
            state=tk.NORMAL if policy.probe else tk.DISABLED
        )
        input_state = tk.NORMAL if policy.edit_inputs else tk.DISABLED
        for button in (
            self.add_button,
            self.txt_button,
            self.excel_button,
            self.remove_button,
            self.clear_button,
            self.output_button,
        ):
            button.configure(state=input_state)
        self.manual_text.configure(state=input_state)
        self.date_entry.configure(state=input_state)
        self.output_entry.configure(state=input_state)
        self.port_entry.configure(state=input_state)
        self.browser_combo.configure(
            state="readonly" if policy.edit_inputs else tk.DISABLED
        )
        self.market_combo.configure(
            state="readonly" if policy.edit_inputs else tk.DISABLED
        )
        self.start_button.configure(
            state=tk.NORMAL if policy.start else tk.DISABLED
        )
        self.pause_button.configure(
            state=tk.NORMAL if policy.pause or policy.resume else tk.DISABLED
        )
        self.stop_button.configure(state=tk.NORMAL if policy.stop else tk.DISABLED)
        self.open_button.configure(
            state=tk.NORMAL if policy.export and self.last_output else tk.DISABLED
        )

    def _open_output(self) -> None:
        if self.last_output is None:
            return
        target = self.last_output.parent
        if platform.system() == "Windows":
            subprocess.Popen(["explorer", str(target)])
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])

    def _on_close(self) -> None:
        if self._closing:
            return
        if self.phase in {RunPhase.RUNNING, RunPhase.PAUSED} and not messagebox.askyesno(
            "退出", "任务仍在运行。停止任务并退出吗？"
        ):
            return
        self._closing = True
        self.phase = RunPhase.STOPPING
        self.status_var.set("正在保存进度并关闭浏览器…")
        self._apply_policy()
        self.worker.shutdown()
        self.root.after(100, self._finish_close)

    def _finish_close(self) -> None:
        if self.worker.is_alive():
            self.root.after(100, self._finish_close)
            return
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    KKdayScraperApp(root)
    root.mainloop()
