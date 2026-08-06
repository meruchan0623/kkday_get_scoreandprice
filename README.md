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

## 币种偏好 Cookie 自动注入

`--market` 只控制进入哪个分站首页，不保证会员状态接口返回 `--currency` 指定的币种。程序在 CDP 连接专用浏览器后、新建页面前，会自动注入持久化的**站点偏好 Cookie** 来设置币种。

- 存储文件：`~/Documents/KKdayScraper/preference_cookies.json`，权限 `0600`。
- 由 `kkday_scraper/cookie_store.py` 管理，只持久化三个非凭据站点偏好：`currency`、`country_lang`、`lang_ui`；session、CSRF、`KKWEB`、`datadome` 等凭据永不写入。
- 正常情况下该文件已存在目标币种（如 `currency=TWD`），无需任何手动操作，CLI 直接即可通过币种门禁。
- Cookie 保留 host-only domain（`www.kkday.com`，不加前导点），以覆盖专用浏览器 Profile 中已有的同名币种 Cookie。

### 重新截获并写入币种 Cookie

当存储文件缺失、币种错误，或出现 `currency_mismatch` 时，用 ego-browser 从已加载 KKday 页面的真实浏览器截获偏好 Cookie：

```bash
ego-browser nodejs <<'EOF'
const task = await useOrCreateTaskSpace('capture kkday currency cookie')
await openOrReuseTab('https://www.kkday.com/zh-tw', { wait: true, timeout: 30 })
await wait(3)
const { cookies } = await cdp('Network.getAllCookies', {})
const keep = cookies.filter(c =>
  ['currency','country_lang','lang_ui'].includes(c.name) &&
  c.domain.replace(/^\./,'').endsWith('kkday.com'))
cliLog(JSON.stringify(keep, null, 2))
EOF
```

然后用 `cookie_store.save_preference_cookies()` 写入（`domain` 保持截获到的原值，不要加前导点）。可一行验证：

```bash
python3 -c "from kkday_scraper.cookie_store import currency_from_store; print(currency_from_store())"
```

输出应为目标币种（如 `TWD`）。写入后重新运行 CLI，`probe_member` 回读即为目标币种。

只有在偏好 Cookie 正确但服务端仍强制返回其他币种时（如依据 IP/账户偏好），才需要在专用浏览器中通过 UI（`button.header__currency` → `.currency` 选项）手动切换，切换后重新截获写回存储文件。不得通过 session/CSRF 等凭据或绕过挑战来设置币种。

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

## Hermes Agent 与 Codex 标准操作流程

以下流程适用于单 URL、多 URL、TXT 和供应商 XLSX 输入。Hermes 主机的精确项目路径、解释器和登录交接规则以 `hermes-agent/skills/kkday-sku-price-scraper-operations/SKILL.md` 为准。Codex 在本地工作区执行本项目 CLI、使用 Computer Use 操作可见浏览器，或交付抓取结果时，也必须遵守本节的参数解析、专用浏览器、安全边界、重跑限制和逐 URL 验收要求；不得因执行主体不同而降低标准。

### 1. 解析并确认运行参数

按优先级确认：输入 → 使用日期 → 市场 → 币种。所有参数都必须显式传入 CLI：

- 用户指定日期时使用该日期；未指定时使用运行主机的下一个自然日。
- 未指定市场时使用 `zh-tw`。
- 未指定币种时使用 `TWD`。
- 同一句存在互相冲突的日期、市场或币种时，先向用户确认。
- 多个 URL 必须分别传入多个 `--url` 参数；TXT/XLSX 必须使用绝对路径。

### 2. 执行运行前检查

每次运行前确认：

1. 当前主机、项目根目录和项目内 Skill 指定的 Python 解释器一致。
2. `/System/Volumes/Data` 可用空间至少为 2 GiB。
3. `openpyxl` 和 `playwright` 可以导入。
4. 当前存在 macOS 图形用户会话，并已安装 Edge 或 Chrome。
5. 本次使用全新的绝对结果目录，不覆盖其他批次。

运行抓取时不得安装或升级依赖、创建临时虚拟环境、改用 GUI、调用 `python -m kkday_scraper.cli` 或运行复制出来的脚本。

### 3. 构造并执行批次命令

标准命令形态：

```bash
cd /Users/tsimclaw/Develop/kkday_get_scoreandprice
RUN_ID="$(date +%Y%m%d_%H%M%S)"
RESULT_DIR="/Users/tsimclaw/Documents/kkday-sku-price-scrape/$RUN_ID"
/usr/local/bin/python3.14 kkday_get_scoreandprice.pyw \
  --url 'https://www.kkday.com/zh-tw/product/121004' \
  --url 'https://www.kkday.com/zh-tw/product/149025' \
  --date 2026-08-06 \
  --market zh-tw \
  --currency TWD \
  --launch-browser \
  --browser edge \
  --result-dir "$RESULT_DIR"
```

解释器路径以项目内 Skill 指定的版本为准（生产主机为 `/usr/local/bin/python3.14`）。在开发机上若 3.14 缺失但 `/usr/local/bin/python3.13` 已能导入 `openpyxl` 与 `playwright`，可使用 3.13（README 要求 3.11+）；运行前用 `python3 -c "import openpyxl, playwright"` 确认依赖可用。项目根目录与结果目录替换为当前主机的实际绝对路径。

默认使用 `--launch-browser` 启动或复用 KKday 专用 Profile。每次会员预检前，CLI 会依据 `--market` 自动导航到对应分站首页：`zh-tw` 为 `https://www.kkday.com/zh-tw`，`zh-hk` 为 `https://www.kkday.com/zh-hk`；这会切换页面分站，但不会伪造、换算或强制修改 KKday 会话返回的币种。只有项目专用浏览器已经准备好、端口明确且实例归属可验证时，才使用 `--cdp-url`；不得同时传入 `--launch-browser` 和 `--cdp-url`。

### 4. 监控 JSON Lines 并按状态分流

保留进程退出码，并关注最后一个 `summary`。处理中按以下规则分流：

- `401`、`403`、HTML challenge、验证码、MFA 或用户接管浏览器：停止自动操作，将项目专用浏览器交给用户。
- `currency_mismatch`：先确认 `preference_cookies.json` 中 `currency` 等于目标币种（见“币种偏好 Cookie 自动注入”），缺失或错误时重新截获写入；若 Cookie 正确仍不生效，再用专用浏览器 UI 切换并回写。不得换算或重标价格。
- 参数或路径机械错误：修正明确错误后最多重试一次。
- 用户完成登录、验证或币种调整并明确确认后：复用同一专用会话最多重跑一次。
- 再次失败：保留原生诊断产物并报告，不进行无限重试。

任何情况下都不得读取、打印或导出 Cookie、密码、Authorization、CSRF、OTP、会员标识或 DevTools WebSocket 标识，也不得复制用户默认浏览器 Profile。

### Computer Use 币种切换（兜底）

程序默认通过持久化偏好 Cookie 自动设置币种（见“币种偏好 Cookie 自动注入”）。仅当 Cookie 正确但服务端仍返回其他币种时，才需要在用户明确授权下用 Computer Use 修改专用浏览器的币种控件：

1. 每次操作前用 `get_app_state` 获取最新可访问性状态；控件语义不足时再查看最新截图。不得复用旧的元素编号、坐标或菜单编号。
2. 在本次 `--market` 对应分站首页定位 `button.header__currency` 打开币种弹层，在 `.currency` 列表中只选择用户明确授权的目标币种。
3. 每次点击、滚动或输入后重新读取 UI 状态。
4. 出现登录、账户选择、验证码、MFA、人机验证、安全警告、权限请求或用户接管浏览器时，立即停止并交还用户。
5. 切换成功后，用 ego-browser 重新截获并写回 `preference_cookies.json`，使后续批次自动生效。
6. 完成切换后必须重新执行一次 CLI 预检/抓取，确认会员状态接口返回的币种与 `--currency` 完全一致；只有此回读成功后才可重跑一次。

不得通过 session/CSRF/Authorization 等凭据、DevTools 脚本注入或请求头篡改币种。如果重跑后仍是 `currency_mismatch`，保留原生诊断产物并报告会话币种未生效。

### 5. 按输入 URL 验收覆盖率

批次级 `product_count` 只表示程序处理了多少个商品，不证明每个商品都有可售价格。交付前必须逐一核对每个输入 URL：

1. 统计该 URL 在 `可售SKU` 中的可信行数。
2. 检查该 URL 是否出现在 `失败与警告`。
3. 如果某 URL 为零行且没有失败，按“指定日期无可售 SKU”报告；不要把其他商品的行数归给它，也不要声称已经取得该商品价格。
4. 如用户要求“价格或产品信息”，零行商品只能交付程序已明确提取的商品/套餐信息；不得从日志猜测价格。

### 6. 完整成功验收与交付

完整成功必须同时满足：

- 进程退出码为 `0`。
- 最终 `summary.products` 与实际已处理输入数一致，且 `summary.failures` 为 `0`。
- `run_summary.json` 为 `status: final`，其中商品数、行数和失败数与工作簿一致。
- `summary.output` 指向本次结果目录内可读取的 `kkday_price_results.xlsx`。
- 工作簿包含 `可售SKU`、`失败与警告`、`运行摘要`。
- 结果目录不存在 `failures.jsonl`。
- 已完成逐 URL 覆盖核对，并区分“有可信价格”“无可售 SKU”和“失败”。

交付时说明使用日期、市场、请求币种、输入商品数、每个 URL 的可信行数、失败数、结果目录和 XLSX 路径。浏览器已打开、会员接口 HTTP 200、XLSX 已生成或批次退出码为 `0`，任何单项都不能替代逐 URL 和最终产物验收。

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
- CLI 不应输出 session Cookie、Authorization、CSRF 或 DevTools WebSocket 会话 ID。唯一被持久化的 Cookie 是 `currency`、`country_lang`、`lang_ui` 三个站点偏好，存于 `preference_cookies.json`（权限 0600），由 `cookie_store` 白名单强制约束。
- `401`、`403` 或 HTML challenge 会阻止批次继续。用户完成验证后，再重新运行命令。
- 目标币种与浏览器实际返回的币种不一致时，程序产生 `currency_mismatch` 失败，不导出可信价格，也不做汇率换算；优先用持久化偏好 Cookie 修正（见上）。
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
