from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest

from kkday_scraper.exporter import RunExporter
from kkday_scraper.models import (
    FailureKind,
    FailureRecord,
    InputItem,
    PriceStatus,
    ProductResult,
    RunConfig,
    SkuRow,
)


def make_product() -> ProductResult:
    item = InputItem(
        "https://www.kkday.com/zh-tw/product/149025-example", vendor="TSIM 網址"
    )
    row = SkuRow(
        vendor=item.vendor,
        input_order=0,
        product_id="149025",
        product_url=item.url,
        product_name="日本 eSIM",
        package_id="476215",
        package_name="每日/无限流量",
        item_id="221992",
        sku_id="sku-1",
        usage_date=date(2026, 7, 22),
        options=("500MB/日", "1 日"),
        available=True,
        currency="KRW",
        sale_price=Decimal("711"),
        official_price=None,
        price_source="single_price.fullday",
        price_status=PriceStatus.TRUSTED,
    )
    failure = FailureRecord(
        FailureKind.API, item.url, "package:2", "HTTP 500", True
    )
    return ProductResult(item, None, (row,), (failure,), ("一个警告",))


def test_checkpoint_writes_stable_workbook_and_failure_ledger(
    tmp_path: Path,
) -> None:
    config = RunConfig(date(2026, 7, 22), tmp_path)
    exporter = RunExporter(config, run_id="20260722_120000")

    output = exporter.checkpoint((make_product(),), final=True)

    assert output.exists()
    workbook = openpyxl.load_workbook(output, data_only=True)
    assert workbook.sheetnames == ["可售SKU", "失败与警告", "运行摘要"]
    sheet = workbook["可售SKU"]
    headers = [cell.value for cell in sheet[1]]
    assert headers[:8] == [
        "厂商",
        "输入序号",
        "商品ID",
        "URL",
        "商品名称",
        "套餐ID",
        "套餐名称",
        "ItemID",
    ]
    assert sheet["M2"].value == 711
    assert exporter.summary_path.exists()
    assert exporter.failures_path.exists()


def test_exact_result_directory_does_not_add_a_timestamp_folder(
    tmp_path: Path,
) -> None:
    result_dir = tmp_path / "chosen-result"
    exporter = RunExporter(
        RunConfig(date(2026, 7, 22), tmp_path),
        result_dir=result_dir,
    )

    output = exporter.checkpoint((make_product(),), final=True)

    assert output == result_dir / "kkday_price_results.xlsx"
    assert exporter.summary_path == result_dir / "run_summary.json"


def test_checkpoint_omits_unavailable_rows_by_default(tmp_path: Path) -> None:
    product = make_product()
    unavailable = product.rows[0].__class__(
        **{
            **product.rows[0].__dict__,
            "sku_id": "closed",
            "available": False,
            "price_status": PriceStatus.UNAVAILABLE,
        }
    )
    product = ProductResult(product.input_item, None, product.rows + (unavailable,))
    exporter = RunExporter(
        RunConfig(date(2026, 7, 22), tmp_path), run_id="20260722_120001"
    )

    output = exporter.checkpoint((product,), final=False)

    workbook = openpyxl.load_workbook(output, data_only=True)
    assert workbook["可售SKU"].max_row == 2


def test_failed_checkpoint_preserves_previous_valid_workbook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exporter = RunExporter(
        RunConfig(date(2026, 7, 22), tmp_path), run_id="20260722_120002"
    )
    output = exporter.checkpoint((make_product(),), final=False)
    previous = output.read_bytes()

    def fail_save(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(openpyxl.Workbook, "save", fail_save)
    with pytest.raises(OSError, match="disk full"):
        exporter.checkpoint((make_product(),), final=True)

    assert output.read_bytes() == previous


def test_remote_text_cannot_become_an_excel_formula(tmp_path: Path) -> None:
    product = make_product()
    dangerous = replace(
        product.rows[0],
        product_name='=HYPERLINK("https://example.invalid")',
        package_name="@SUM(1,1)",
    )
    product = ProductResult(product.input_item, None, (dangerous,))
    exporter = RunExporter(
        RunConfig(date(2026, 7, 22), tmp_path), run_id="20260722_120003"
    )

    output = exporter.checkpoint((product,), final=True)

    workbook = openpyxl.load_workbook(output, data_only=False)
    assert workbook["可售SKU"]["E2"].value.startswith("'=")
    assert workbook["可售SKU"]["G2"].value.startswith("'@")
