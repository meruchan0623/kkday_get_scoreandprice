# KKday SKU 价格抓取工具

通过已登录的 Chrome/Edge 浏览器会话抓取 KKday 商品在指定使用日期的可售 SKU 和价格，并导出 Excel。默认抓取下一个自然日、台湾市场和新台币（TWD）；三者均可用参数覆盖。

本文优先说明 Agent 如何运行 CLI。当前支持 `zh-tw`、`zh-hk` 市场；Python 要求 3.11 或以上。

## Agent 快速运行

### 1. 安装

```bash
cd /Users/tashima_meru/Develop/kkday_get_scoreandprice
python3 -m pip install -e '.[dev]'
```

### 2. 运行单个商品

推荐让 CLI 启动或复用独立的 Edge 调试浏览器：

```bash
cd /Users/tashima_meru/Develop/kkday_get_scoreandprice
python3 kkday_get_scoreandprice.pyw \
  --url 'https://www.kkday.com/zh-tw/product/149025-example' \
  --date 2026-07-22 \
  --market zh-tw \
  --launch-browser \
  --browser edge \
  --result-dir "$HOME/Downloads/KKday_scraping/agent-result"
```

首次启动时可以在打开的专用浏览器中手动登录 KKday。未登录时程序会明确提示，但仍会继续首商品的公开页面、价格日历和 SKU 接口预检；只有业务预检失败才会停止。

不要自动填写账号、密码或验证码，也不要尝试绕过挑战页。

### 3. 连接已经开放 CDP 的浏览器

如果用户已有可连接的 Chrome/Edge 调试会话：

```bash
python3 kkday_get_scoreandprice.pyw \
  --url 'https://www.kkday.com/zh-hk/product/149025-example' \
  --date 2026-07-22 \
  --market zh-hk \
  --cdp-url 'http://127.0.0.1:9222' \
  --result-dir "$HOME/Downloads/KKday_scraping/agent-result"
```

不要同时传 `--launch-browser` 和自定义 `--cdp-url` 来表达两个候选会话。传入 `--launch-browser` 时，程序使用它启动或复用的专用浏览器端点。

## CLI 入口规则

```bash
python3 kkday_get_scoreandprice.pyw [参数]
```

- 无任何参数：打开 GUI。
- 有参数：进入 CLI。
- CLI 至少需要一个 `--url` 或 `--input`；否则退出码为 `2`。
- 查看真实参数：`python3 kkday_get_scoreandprice.pyw --help`。

不要使用 `python3 -m kkday_scraper.cli` 作为文档约定入口；项目入口是根目录的 `kkday_get_scoreandprice.pyw`。

## 输入方式

`--url` 和 `--input` 都可以重复，且可以混用。程序会规范化 URL 并去重。

### 多个 URL

```bash
python3 kkday_get_scoreandprice.pyw \
  --url 'https://www.kkday.com/zh-tw/product/149025-example-a' \
  --url 'https://www.kkday.com/zh-tw/product/123456-example-b' \
  --date 2026-07-22 \
  --launch-browser \
  --browser auto
```

### TXT 文件

TXT 使用 UTF-8，每行一个 KKday 商品 URL：

```bash
python3 kkday_get_scoreandprice.pyw \
  --input '/absolute/path/urls.txt' \
  --date 2026-07-22 \
  --launch-browser
```

### XLSX 文件

CLI 读取工作簿的第一个工作表：

- 第 1 行：厂商名，每列一个厂商。
- 第 2 行起：该列厂商对应的 KKday 商品 URL。
- 没有厂商表头的链接或非 KKday URL 会被忽略，并输出 `warning` 事件。

```bash
python3 kkday_get_scoreandprice.pyw \
  --input '/absolute/path/vendors.xlsx' \
  --date 2026-07-22 \
  --launch-browser \
  --browser edge
```

只接受 `kkday.com` 或 `www.kkday.com` 的商品 URL；查询参数和片段不会保留。

## 参数契约

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `--url URL` | 无 | 商品 URL，可重复 |
| `--input PATH` | 无 | `.txt` 或 `.xlsx` 文件，可重复 |
| `--date YYYY-MM-DD` | 本机下一个自然日 | 使用日期；可由自然语言或参数覆盖 |
| `--market {zh-tw,zh-hk}` | `zh-tw` | KKday 请求市场 |
| `--currency CODE` | `TWD` | 期望结果币种；实际浏览器会话返回的币种不一致时失败，不换算、不伪造 |
| `--output DIR` | `~/Downloads/KKday_scraping` | 输出根目录，程序在其下创建 `YYYYMMDD_HHMMSS` 子目录 |
| `--result-dir DIR` | 无 | 直接作为最终目录，不创建时间戳子目录；优先于 `--output` |
| `--cdp-url URL` | `http://127.0.0.1:9222` | 已开放 CDP 的浏览器地址 |
| `--launch-browser` | 关闭 | 启动或复用 KKday 专用调试浏览器 |
| `--browser {auto,edge,chrome}` | `auto` | 仅配合 `--launch-browser`；`auto` 优先 Edge |

未传 `--date` 时，CLI 使用本机下一个自然日；未传 `--market`、`--currency` 时分别使用 `zh-tw`、`TWD`。Agent 应在自然语言中提取到明确日期、市场或币种时传入对应参数，并优先使用绝对路径。需要可预测的产物位置时使用 `--result-dir`；需要保留多次运行时使用 `--output`。

## 标准输出与退出码

CLI 的标准输出是 JSON Lines：每行都是一个独立 JSON 对象，适合 Agent 逐行解析。常见 `type` 包括：

- `browser`：专用调试浏览器已就绪。
- `progress` / 其他任务事件：当前阶段和进度。
- `warning`：输入项被忽略或存在非致命问题。
- `blocked`：浏览器或 KKday 会话不可用。
- `auth_required`：用户需要先在浏览器登录。
- `summary`：运行结束汇总，包含 `products`、`trusted_rows`、`failures` 和 `output`。
- `error`：参数、文件或运行时错误。

示例：

```json
{"type":"summary","message":"抓取完成","products":1,"trusted_rows":8,"failures":0,"output":"/Users/example/Downloads/KKday_scraping/agent-result/kkday_price_results.xlsx"}
```

| 退出码 | 含义 | Agent 应采取的动作 |
| --- | --- | --- |
| `0` | 所有已处理商品成功且没有失败项 | 读取最后一个 `summary`，核对 `output` |
| `2` | 参数、输入文件或商品 URL 无效 | 修正命令或输入文件后重试 |
| `3` | 浏览器、会员接口或会话不可用，或发生未分类运行异常 | 根据最后一个 `blocked` 或 `error` 处理；若商品接口明确要求登录，再交还用户 |
| `4` | 任务已执行，但至少一个商品失败，或没有形成成功商品结果 | 检查 `summary`、`failures.jsonl` 和工作簿，不要因为 XLSX 已存在就宣称全部成功 |

Agent 必须以进程退出码作为最终成功判断，不能只依据输出目录或 XLSX 是否存在。输出目录可能在浏览器检查前就已创建，任务失败时也可能保留部分工作簿。

## 输出文件

最终结果目录包含：

- `kkday_price_results.xlsx`：工作表为 `可售SKU`、`失败与警告`、`运行摘要`。
- `run_summary.json`：运行 ID、使用日期、状态、商品数、行数、失败数和工作簿路径。
- `failures.jsonl`：仅在存在失败项时生成；成功运行会移除同目录中的旧失败文件。

`--output` 示例目录：

```text
~/Downloads/KKday_scraping/20260722_143000/
```

`--result-dir /tmp/kkday-result` 则直接写入：

```text
/tmp/kkday-result/kkday_price_results.xlsx
/tmp/kkday-result/run_summary.json
/tmp/kkday-result/failures.jsonl  # 仅失败时存在
```

## 浏览器与安全边界

- `--launch-browser` 使用独立持久化 Profile：`~/Library/Application Support/KKdayScraper/browser-profiles/edge` 或 `chrome`。
- 程序不会复制、重启或关闭用户的默认浏览器 Profile。
- 登录、验证码和挑战处理全部由用户在浏览器中完成。
- CLI 不应输出 Cookie、Authorization、CSRF 或 DevTools WebSocket 会话 ID。
- `401`、`403` 或 HTML challenge 会阻止批次继续。用户完成验证后，再重新运行命令。
- 目标币种与浏览器实际返回的币种不一致时，程序产生 `currency_mismatch` 失败，不导出可信价格，也不做汇率换算。
- `schema_unknown`、`missing_price`、`minimum_mismatch` 不应视为可信价格。

## GUI

不传参数即可打开桌面界面：

```bash
python3 kkday_get_scoreandprice.pyw
```

GUI 适合人工选择浏览器、登录、导入输入和查看状态；Agent 自动化应使用上面的 CLI 契约。

## 开发验证

```bash
python3 -m pytest -q -m 'not live'
python3 -m compileall -q kkday_scraper kkday_get_scoreandprice.pyw
```

授权浏览器的可选实时契约测试：

```bash
KKDAY_CDP_URL='http://127.0.0.1:9222' \
KKDAY_LIVE_URL='https://www.kkday.com/zh-tw/product/149025-example' \
KKDAY_USAGE_DATE='2026-07-22' \
python3 -m pytest tests/test_live_kkday_contract.py -m live -q
```
