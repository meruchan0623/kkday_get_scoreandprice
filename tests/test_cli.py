from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from kkday_scraper import cli
from kkday_scraper.cli import build_parser, load_inputs
from kkday_scraper.models import RunResult, SessionProbe


def test_cli_accepts_a_complete_codex_driven_run(tmp_path: Path) -> None:
    args = build_parser().parse_args(
        [
            "--url",
            "https://www.kkday.com/zh-tw/product/149025-example",
            "--date",
            "2026-07-22",
            "--output",
            str(tmp_path),
            "--launch-browser",
            "--browser",
            "edge",
            "--market",
            "zh-hk",
        ]
    )

    assert args.urls == [
        "https://www.kkday.com/zh-tw/product/149025-example"
    ]
    assert args.usage_date == date(2026, 7, 22)
    assert args.output == tmp_path
    assert args.launch_browser is True
    assert args.browser == "edge"
    assert args.market == "zh-hk"


def test_cli_accepts_an_exact_result_directory(tmp_path: Path) -> None:
    result_dir = tmp_path / "kkday-result"

    args = build_parser().parse_args(
        [
            "--url",
            "https://www.kkday.com/zh-tw/product/149025-example",
            "--result-dir",
            str(result_dir),
        ]
    )

    assert args.result_dir == result_dir


def test_cli_defaults_to_next_calendar_day_taiwan_and_twd() -> None:
    args = build_parser().parse_args(
        ["--url", "https://www.kkday.com/zh-tw/product/149025-example"]
    )

    assert args.usage_date == date.today() + timedelta(days=1)
    assert args.market == "zh-tw"
    assert args.currency == "TWD"


def test_cli_allows_currency_to_override_the_twd_default() -> None:
    args = build_parser().parse_args(
        [
            "--url",
            "https://www.kkday.com/zh-hk/product/149025-example",
            "--market",
            "zh-hk",
            "--currency",
            "USD",
        ]
    )

    assert args.market == "zh-hk"
    assert args.currency == "USD"


def test_cli_loads_and_deduplicates_url_and_txt_inputs(tmp_path: Path) -> None:
    url = "https://www.kkday.com/zh-tw/product/149025-example"
    source = tmp_path / "urls.txt"
    source.write_text(f"{url}\n{url}\n", encoding="utf-8")

    items = load_inputs([url], [source])

    assert [item.url for item in items] == [url]


def test_cli_rejects_a_run_without_any_input() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as error:
        parser.parse_args(["--date", "2026-07-22"])

    assert error.value.code == 2


def test_cli_continues_to_public_product_preflight_without_login(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[str] = []

    class FakeSession:
        def __init__(self, _config):
            pass

        def connect(self, allow_launch=False, endpoint=None):
            pass

        def probe_member(self, market):
            return SessionProbe(
                True,
                True,
                False,
                "TWD",
                market,
                "https://www.kkday.com/zh-tw",
            )

        def close(self):
            pass

    class FakeRunner:
        def __init__(self, _session):
            pass

        def run(self, items, config, control, reporter, checkpoint):
            calls.append(items[0].url)
            now = datetime.now()
            return RunResult((), None, now, now)

    monkeypatch.setattr(cli, "BrowserSession", FakeSession)
    monkeypatch.setattr(cli, "TaskRunner", FakeRunner)

    code = cli.main(
        [
            "--url",
            "https://www.kkday.com/zh-tw/product/149025-example",
            "--output",
            str(tmp_path),
        ]
    )

    assert calls == ["https://www.kkday.com/zh-tw/product/149025-example"]
    assert code == 4
    assert "公开商品接口" in capsys.readouterr().out
