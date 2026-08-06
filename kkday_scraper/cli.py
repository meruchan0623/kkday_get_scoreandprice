from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Sequence

from .browser_session import BrowserSession
from .ego_browser import build_agent_handoff
from .exporter import RunExporter
from .inputs import deduplicate_inputs, load_manual_urls, load_txt, load_vendor_excel
from .models import (
    AppEvent,
    EventKind,
    RunConfig,
    RunPhase,
    SUPPORTED_MARKETS,
)
from .task_runner import RunControl, TaskRunner


class _RunParser(argparse.ArgumentParser):
    def parse_args(self, args: Sequence[str] | None = None, namespace=None):
        parsed = super().parse_args(args, namespace)
        if not parsed.urls and not parsed.inputs:
            self.error("至少需要一个 --url 或 --input")
        return parsed


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("日期必须是 YYYY-MM-DD") from exc


def _currency(value: str) -> str:
    normalized = value.strip().upper()
    if (
        len(normalized) != 3
        or not normalized.isascii()
        or not normalized.isalpha()
    ):
        raise argparse.ArgumentTypeError("币种必须是三个英文字母，例如 TWD")
    return normalized


def build_parser() -> argparse.ArgumentParser:
    parser = _RunParser(
        prog="kkday_get_scoreandprice.pyw",
        description="通过 ego-browser task space 抓取 KKday SKU 价格",
    )
    parser.add_argument("--url", dest="urls", action="append", default=[], help="KKday 商品 URL，可重复")
    parser.add_argument("--input", dest="inputs", action="append", type=Path, default=[], help="TXT 或 XLSX 输入文件，可重复")
    parser.add_argument("--date", dest="usage_date", type=_iso_date, default=date.today() + timedelta(days=1), help="使用日期，默认下一个自然日")
    parser.add_argument("--output", type=Path, default=Path.home() / "Downloads" / "KKday_scraping", help="输出根目录")
    parser.add_argument("--result-dir", type=Path, help="最终结果目录；不会再创建时间戳子目录")
    parser.add_argument("--ego-task-space", help="复用的 ego-browser task space 名称；默认按市场生成")
    parser.add_argument("--market", choices=SUPPORTED_MARKETS, default="zh-tw", help="KKday 站点，默认 zh-tw")
    parser.add_argument("--currency", type=_currency, default="TWD", help="期望结果币种，默认 TWD")
    return parser


def load_inputs(urls: Sequence[str], paths: Sequence[Path]):
    items = load_manual_urls("\n".join(urls))
    for path in paths:
        suffix = path.suffix.lower()
        if suffix == ".txt":
            items.extend(load_txt(path, len(items)))
        elif suffix == ".xlsx":
            loaded, warnings = load_vendor_excel(path, len(items))
            items.extend(loaded)
            for warning in warnings:
                _emit("warning", warning)
        else:
            raise ValueError(f"不支持的输入文件：{path}（仅支持 .txt/.xlsx）")
    return deduplicate_inputs(items)


def _emit(kind: str, message: str, **details: object) -> None:
    print(
        json.dumps(
            {"type": kind, "message": message, **details},
            ensure_ascii=False,
            default=str,
        ),
        flush=True,
    )


def _report(event: AppEvent) -> None:
    details: dict[str, object] = {}
    if event.phase is not None:
        details["phase"] = event.phase.value
    if event.current is not None:
        details["current"] = event.current
    if event.total is not None:
        details["total"] = event.total
    _emit(event.kind.value, event.message, **details)


def _emit_handoff(event: dict[str, object]) -> None:
    details = dict(event)
    kind = str(details.pop("type"))
    message = str(details.pop("message"))
    _emit(kind, message, **details)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        items = load_inputs(args.urls, args.inputs)
        if not items:
            raise ValueError("输入中没有有效的 KKday 商品 URL")
        config = RunConfig(
            usage_date=args.usage_date,
            output_dir=args.output.expanduser(),
            market=args.market,
            currency=args.currency,
            ego_task_space=args.ego_task_space,
            requested_count=len(items),
        )
        exporter = RunExporter(
            config,
            result_dir=args.result_dir.expanduser() if args.result_dir else None,
        )
        session = BrowserSession(config)
        try:
            session.connect()
            probe = session.probe_member(config.market)
            if not probe.member_api_ready:
                session.preserve_for_handoff()
                _emit_handoff(build_agent_handoff(
                    task_space_id=session.task_space_id,
                    task_space_name=session.task_space_name,
                    reason=probe.block_reason or "KKday ego-browser 会话不可用",
                ))
                return 3
            if not probe.is_login:
                _emit("warning", "KKday 会员未登录；继续验证公开商品接口")

            result = TaskRunner(session).run(
                items,
                config,
                RunControl(),
                _report,
                exporter.checkpoint,
            )
            if result.terminal_phase is RunPhase.BLOCKED:
                if hasattr(session, "preserve_for_handoff"):
                    session.preserve_for_handoff()
                failure = result.failures[-1] if result.failures else None
                _emit_handoff(build_agent_handoff(
                    task_space_id=getattr(session, "task_space_id", None),
                    task_space_name=getattr(
                        session, "task_space_name", config.ego_task_space or f"kkday-sku-price-{config.market}"
                    ),
                    reason=failure.message if failure else "KKday 页面需要可见验证",
                    product_url=failure.url if failure else None,
                ))
        finally:
            session.close()
            exporter.close()

        failures = sum(len(product.failures) for product in result.products)
        trusted = sum(len(product.trusted_rows) for product in result.products)
        _emit(
            "summary",
            "抓取完成" if failures == 0 else "抓取结束，但存在失败项",
            products=len(result.products),
            trusted_rows=trusted,
            failures=failures,
            output=str(result.output_path) if result.output_path else None,
            terminal_phase=result.terminal_phase.value,
            requested=result.requested_count,
            processed=result.processed_count,
            final_checkpoint_saved=result.final_checkpoint_saved,
        )
        successful = (
            result.terminal_phase is RunPhase.COMPLETED
            and result.requested_count > 0
            and result.processed_count == result.requested_count
            and result.final_checkpoint_saved
            and failures == 0
        )
        return 0 if successful else 4
    except (OSError, ValueError) as exc:
        _emit("error", str(exc))
        return 2
    except Exception as exc:
        _emit("error", str(exc))
        return 3


if __name__ == "__main__":
    sys.exit(main())
