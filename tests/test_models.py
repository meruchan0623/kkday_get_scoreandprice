from datetime import date
from decimal import Decimal
from pathlib import Path

from kkday_scraper.models import (
    InputItem,
    PriceStatus,
    ReadinessReport,
    RunConfig,
    RunPhase,
    SessionProbe,
    SkuRow,
    market_homepage,
)


def test_run_config_has_safe_finite_defaults(tmp_path: Path) -> None:
    config = RunConfig(usage_date=date(2026, 7, 22), output_dir=tmp_path)

    assert config.market == "zh-tw"
    assert config.currency == "TWD"
    assert config.ego_task_space is None
    assert config.request_timeout_ms == 30_000
    assert config.request_retry_delays == (1.0, 3.0)
    assert config.product_delay_range == (2.0, 4.0)
    assert config.package_delay_range == (0.4, 0.9)


def test_sku_row_keeps_sale_and_official_price_separate() -> None:
    row = SkuRow(
        vendor="手动输入",
        input_order=0,
        product_id="149025",
        product_url="https://www.kkday.com/zh-tw/product/149025-example",
        product_name="日本 eSIM",
        package_id="1982144",
        package_name="总量 eSIM",
        item_id="1727921",
        sku_id="6a7d217fd4e41d222a768a73de2a2ab7",
        usage_date=date(2026, 7, 22),
        options=("總量10GB", "3 日"),
        available=True,
        currency="KRW",
        sale_price=Decimal("10741"),
        official_price=Decimal("21483"),
        price_source="single_price.fullday",
        price_status=PriceStatus.TRUSTED,
    )

    assert row.sale_price == Decimal("10741")
    assert row.official_price == Decimal("21483")
    assert row.option_text == "總量10GB | 3 日"


def test_input_item_retains_excel_origin() -> None:
    item = InputItem(
        url="https://www.kkday.com/zh-tw/product/149025-example",
        vendor="TSIM 網址",
        input_order=2,
        source_path=Path("vendors.xlsx"),
        source_row=4,
        source_column=1,
    )

    assert item.source_row == 4
    assert item.source_column == 1


def test_member_probe_does_not_claim_business_readiness() -> None:
    probe = SessionProbe(
        connected=True,
        member_api_ready=True,
        is_login=True,
        currency="KRW",
        market="zh-tw",
        page_url="https://www.kkday.com/zh-tw",
    )
    report = ReadinessReport.from_member_probe(probe)

    assert report.browser_connected is True
    assert report.member_api_ready is True
    assert report.product_page_ready is None
    assert report.price_calendar_ready is None
    assert report.sku_api_ready is None
    assert report.business_ready is False


def test_verifying_is_a_distinct_run_phase() -> None:
    assert RunPhase.VERIFYING.value == "verifying"


def test_market_homepage_supports_the_requested_non_default_markets() -> None:
    assert market_homepage("ja-jp") == "https://www.kkday.com/ja-jp"
    assert market_homepage("ja") == "https://www.kkday.com/ja"
    assert market_homepage("zh-cn") == "https://www.kkday.com/zh-cn"
    assert market_homepage("en") == "https://www.kkday.com/en"
