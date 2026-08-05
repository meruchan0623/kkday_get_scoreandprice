from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import openpyxl

from .models import InputItem


PRODUCT_PATH_RE = re.compile(r"^/[a-z]{2}-[a-z]{2}/product/([A-Za-z0-9_-]+)(?:-|$|/)", re.IGNORECASE)


def normalize_product_url(raw: str) -> str:
    value = raw.strip()
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or parts.hostname not in {"kkday.com", "www.kkday.com"}:
        raise ValueError(f"不是有效的 KKday 商品 URL：{raw}")
    if PRODUCT_PATH_RE.search(parts.path) is None:
        raise ValueError(f"不是有效的 KKday 商品 URL：{raw}")
    return urlunsplit(("https", "www.kkday.com", parts.path, "", ""))


def load_manual_urls(raw: str, start_order: int = 0) -> list[InputItem]:
    items: list[InputItem] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        items.append(InputItem(url=normalize_product_url(line), input_order=start_order + len(items)))
    return items


def load_txt(path: Path, start_order: int = 0) -> list[InputItem]:
    items: list[InputItem] = []
    for row_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        items.append(
            InputItem(
                url=normalize_product_url(line),
                input_order=start_order + len(items),
                source_path=path,
                source_row=row_number,
            )
        )
    return items


def load_vendor_excel(path: Path, start_order: int = 0) -> tuple[list[InputItem], list[str]]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    workbook.close()
    if not rows:
        raise ValueError("Excel 没有可读取的工作表内容")

    headers = [str(value).strip() if value is not None else "" for value in rows[0]]
    items: list[InputItem] = []
    warnings: list[str] = []
    for row_index, row in enumerate(rows[1:], start=2):
        for column_index, value in enumerate(row, start=1):
            text = str(value).strip() if value is not None else ""
            if not text:
                continue
            vendor = headers[column_index - 1] if column_index <= len(headers) else ""
            if not vendor:
                warnings.append(f"忽略无厂商表头的链接：工作表第 {row_index} 行，第 {column_index} 列")
                continue
            try:
                url = normalize_product_url(text)
            except ValueError:
                warnings.append(f"忽略非 KKday 商品 URL：工作表第 {row_index} 行，第 {column_index} 列：{text}")
                continue
            items.append(
                InputItem(
                    url=url,
                    vendor=vendor,
                    input_order=start_order + len(items),
                    source_path=path,
                    source_row=row_index,
                    source_column=column_index,
                )
            )
    return items, warnings


def deduplicate_inputs(items: list[InputItem]) -> list[InputItem]:
    seen: set[tuple[str, str]] = set()
    result: list[InputItem] = []
    for item in sorted(items, key=lambda candidate: candidate.input_order):
        key = (item.vendor, item.url)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
