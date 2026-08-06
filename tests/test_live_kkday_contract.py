import os
from datetime import date, timedelta
from pathlib import Path

import pytest

from kkday_scraper.browser_api import BrowserApiClient
from kkday_scraper.browser_session import BrowserSession
from kkday_scraper.models import InputItem, RunConfig
from kkday_scraper.product_scraper import extract_product_snapshot
from kkday_scraper.sku_parser import (
    package_minimum,
    parse_item_payload,
    validate_package_minimum,
)


pytestmark = pytest.mark.live


def test_live_browser_context_returns_complete_sku_prices(tmp_path: Path) -> None:
    url = os.environ.get("KKDAY_LIVE_URL")
    task_space = os.environ.get("KKDAY_EGO_TASK_SPACE")
    if not url or not task_space:
        pytest.skip("set KKDAY_LIVE_URL and KKDAY_EGO_TASK_SPACE to run live contract test")

    usage_date = date.fromisoformat(
        os.environ.get("KKDAY_USAGE_DATE", date.today().isoformat())
    )
    config = RunConfig(
        usage_date=usage_date,
        output_dir=tmp_path,
        ego_task_space=task_space,
    )
    session = BrowserSession(config)
    try:
        session.connect(allow_launch=False)
        session.page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        session.page.wait_for_function(
            "() => Boolean(window.__NUXT__?.pinia?.['option-section']?.packages)",
            timeout=45_000,
        )
        probe = session.probe_member(config.market)
        assert probe.member_api_ready, probe.block_reason
        snapshot = extract_product_snapshot(session.page, url)
        api = BrowserApiClient(
            session.page,
            config.market,
            config.request_timeout_ms,
        )
        end_date = usage_date + timedelta(days=40)
        calendar = api.fetch_package_calendar(
            snapshot.product_id, usage_date, end_date
        )

        total_available = 0
        for package in snapshot.packages:
            payload = api.fetch_items_data(
                package.package_id,
                package.item_ids,
                usage_date,
                end_date,
            )
            package_rows = []
            for item_id in package.item_ids:
                package_rows.extend(
                    parse_item_payload(
                        payload=payload,
                        input_item=InputItem(url),
                        product_id=snapshot.product_id,
                        product_name=snapshot.name,
                        package=package,
                        item_id=item_id,
                        usage_date=usage_date,
                        currency=probe.currency,
                    )
                )
            available = [row for row in package_rows if row.available]
            total_available += len(available)
            assert available
            assert all(row.sale_price is not None for row in available)
            assert validate_package_minimum(
                package_rows,
                package_minimum(calendar, package.package_id, usage_date),
            ) == (True, "")

        assert total_available > 0
    finally:
        session.close()
