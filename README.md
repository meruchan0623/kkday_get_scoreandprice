# KKday SKU 价格抓取工具

本项目通过 ego-browser task space 复用用户已有的 KKday 登录状态，在浏览器页面上下文内读取商品、套餐、日历和 SKU 价格，并导出 Excel。ego-browser 是唯一浏览器运行时；项目不启动备用浏览器，也不接受旧浏览器调试端点。

## 运行环境

- 系统 `python3 >= 3.11`；任何电脑上都不得创建、查找、激活或使用 venv。
- Python 依赖只有 `openpyxl`；ego-browser 由 ego lite 提供，不通过 pip 安装。
- 必须在可以运行 ego lite 的图形登录会话中执行。

验证：

```bash
python3 --version
python3 -c 'import openpyxl; print("runtime-ok")'
```

## CLI

抓取单个商品：

```bash
python3 -m kkday_scraper.cli \
  --url 'https://www.kkday.com/zh-tw/product/149025-example' \
  --date '2026-08-07' \
  --market zh-tw \
  --currency TWD \
  --ego-task-space 'kkday-sku-price-zh-tw' \
  --output "$HOME/Downloads/KKday_scraping"
```

抓取 TXT/XLSX 输入：

```bash
python3 -m kkday_scraper.cli \
  --input '/absolute/path/products.txt' \
  --date '2026-08-07' \
  --market zh-tw \
  --currency TWD \
  --ego-task-space 'kkday-20-products' \
  --result-dir '/absolute/path/result'
```

主要参数：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--url URL` | — | 商品 URL，可重复 |
| `--input PATH` | — | TXT 或 XLSX，可重复 |
| `--date YYYY-MM-DD` | 明天 | 使用日期 |
| `--market {zh-tw,zh-hk,ja-jp,ja,zh-cn,en}` | `zh-tw` | 可选的 URL 无市场段回退站点；含受支持市场段的商品 URL 会自动使用自身市场 |
| `--currency CODE` | `TWD` | 期望币种；不换算 |
| `--ego-task-space NAME` | `kkday-sku-price-{market}` | 要复用的 task space |
| `--output DIR` | Downloads 下目录 | 创建独立运行目录 |
| `--result-dir DIR` | — | 使用精确结果目录并加锁 |

### 多市场单任务合并

单个 CLI 任务可同时传入来自多个 KKday 市场（`zh-hk`、`zh-tw`、`ja-jp`、`ja`、`zh-cn`、`en`）的商品 URL。每个 URL 的 market 会从路径自动识别，抓取时逐商品切换浏览器 market 请求头；**所有抓取目标合并进一张「抓取结果」工作表输出**，每个 SKU 行带「市场」列区分，最终交付**同一个原生 `kkday_price_results.xlsx`**，不再按市场拆分多个文件。`--market` 是可选参数，仅作为 URL 缺少受支持市场段或市场段不受支持时的回退值；`--currency` 仍为全任务期望币种（浏览器实际服务的币种会按行记录，不伪造）。

```bash
python3 -m kkday_scraper.cli \
  --url 'https://www.kkday.com/zh-hk/product/121499-example' \
  --url 'https://www.kkday.com/zh-tw/product/155669-example' \
  --date '2026-08-08' \
  --currency USD \
  --ego-task-space 'kkday-mixed-market' \
  --result-dir '/absolute/path/mixed-result'
```

同一个 task space 同一时间只允许一个批次。所有页面导航、JavaScript 和带登录态的请求都由 ego-browser 完成；Python 不读取登录 Cookie、密码、Token 或浏览器内部连接信息。

### 价格事实来源（不可降级）

SKU 价格不是从页面 DOM、按钮文案或商品卡片最小价读取。页面/SSR 只用于取得商品、套餐与 item ID；每个导出的可信 SKU 行必须同时满足：

1. 售价来自浏览器登录上下文中 `GET /api/_nuxt/product/fetch-items-data` 的 `data[item].item.skus[].single_price.fullday`；
2. 可售状态来自同一接口的日期 `calendar` / `closeList`；
3. 该套餐的 SKU 最低售价必须与独立 `GET /api/_nuxt/product/fetch-packages-price-calendar` 的日期 `min_price` 一致。

接口结构缺失、动态价格结构未验证或最低价不一致时，程序失败关闭/标记 partial，绝不以 DOM 显示价补填。

## 挑战与接管

若 KKday 返回 401、403、HTML 挑战或 DataDome 页面，CLI 输出一行 `handoff_required` JSON，并保留当前 task space。字段包含 task space 名称/ID、商品 URL、原因、Agent 恢复提示词和 `retry_limit: 1`。

Hermes Agent 或其他调用 Agent必须复用同一个 task space，可使用 ego-browser 或 Computer Use 做普通可见操作。若浏览器已记住并自动填充账号密码，只可点击一次登录按钮；不得读取或导出凭据。CAPTCHA、MFA、账号选择和安全确认必须通过 ego-browser handoff 交给真人。真人明确完成后才能接管原 task space并按完全相同参数重跑一次；不得无限重试、创建替代空间或尝试规避安全机制。

退出码：

| 退出码 | 含义 |
|---|---|
| `0` | 全部输入已处理、最终检查点已保存且无失败 |
| `2` | 参数、输入、输出或系统运行时错误 |
| `3` | 批次开始前会话不可用，需要协作/人工处理 |
| `4` | 批次部分完成、被挑战或存在商品失败 |

## 输出与验收

- 完整结果：`kkday_price_results.xlsx`
- 中间/阻断结果：`kkday_price_results.partial.xlsx`
- 运行摘要：`run_summary.json`
- 失败明细：`failures.jsonl`（仅有失败时存在）

Excel 工作表：

- `抓取结果`：可信商品与 SKU 明细；
- `失败商品`：失败、警告及 `no_available_sku` 明确业务结果；
- `运行汇总`：输入/处理/成功/失败数量、可信行数、状态和 task space。

每个输入 URL 必须出现在结果或失败/无可售记录中。XLSX 已存在不代表成功；完整成功必须同时满足退出码 `0`、请求数等于处理数、失败数为 `0`、最终 XLSX 可重新打开、`run_summary.json` 为 final 且不存在 `failures.jsonl`。

## GUI

```bash
python3 kkday_get_scoreandprice.pyw
```

GUI 提供 task space 名称、task ID、打开/复用 ego-browser、重新检测和复制 Agent 恢复提示词。浏览器调用始终在单一后台工作线程执行，Tk 控件只在主线程更新。

## 开发验证

```bash
python3 -m pytest -q -m 'not live'
python3 -m compileall -q kkday_scraper
python3 -m pip check
python3 -m kkday_scraper.cli --help
```
