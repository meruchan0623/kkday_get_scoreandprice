---
name: kkday-sku-price-scraper-operations
description: Use when Hermes or Hemis is asked to query, run, retry, diagnose, or deliver KKday SKU prices from product URLs, TXT files, or vendor XLSX files on the TSimClaw Mac.
---

# KKday SKU 价格抓取（Hermes 操作规范）

本文件是此项目唯一的运行规范。它仅适用于以下项目，不能复制到全局 Skill 目录，也不能改用其他 KKday 工具：

```text
项目：/Users/tsimclaw/Develop/kkday_get_scoreandprice
解释器：/usr/local/bin/python3.14
入口：/Users/tsimclaw/Develop/kkday_get_scoreandprice/kkday_get_scoreandprice.pyw
```

不得创建或使用项目虚拟环境；不得使用 macOS 自带的 `/usr/bin/python3`、GUI、`python -m kkday_scraper.cli` 或复制出来的脚本。

## 触发范围

当用户要求「查 KKday 价格」「抓取这个链接明天的价格」「按日期查套餐」「重跑 KKday 价格」「解释抓取失败」或交付已抓取的价格文件时，读取并遵守本 Skill。

输入必须至少包含其一：

- 一个 `kkday.com` / `www.kkday.com` 商品链接；
- 一个绝对路径的 `.txt` 或 `.xlsx` 输入文件。

只接受 KKday 商品 URL。XLSX 的首行是供应商名称、其后行为链接；只读该源文件，绝不原地修改。

## 自然语言解析优先级

按以下顺序将自然语言解析成一次运行参数；越靠前的明确表达优先级越高。

1. **输入目标**：明确的 URL 或绝对输入文件路径必填；缺失时先索取，不能启动浏览器猜测商品。
2. **日期**：明确 ISO 日期（`YYYY-MM-DD`）最高优先；其后为「今天」「明天」「后天」等相对日期。用户未给日期时，取运行主机本地日历的**下一个自然日**，并显式传入 `--date YYYY-MM-DD`，绝不隐式使用当天。
3. **市场**：明确市场覆盖默认值。台湾／台灣／`zh-tw` 映射 `--market zh-tw`；香港／`zh-hk` 映射 `--market zh-hk`。未指定时为台湾 `zh-tw`。
4. **货币**：明确三字母币种代码或货币名称覆盖默认值。新台币／新台幣／台币／台幣映射 `TWD`；美元映射 `USD`；港币／港幣映射 `HKD`。未指定时为 `TWD`。
5. **冲突处理**：同一句出现两个不同市场、两个不同货币，或日期无法唯一确定时，先向用户确认；不得先开浏览器再猜测。市场和货币可独立，例如「台湾市场美元」是 `zh-tw` 加 `USD`，并不冲突。

所有默认值都要在实际命令中显式传入，便于日志和复现。

## 自然语言到参数映射

| 用户表达 | 解析结果 | 必须传入的核心参数 |
| --- | --- | --- |
| `抓取这个链接明天的价格 https://www.kkday.com/zh-tw/product/121004` | 明天、台湾、台币 | `--date <明天YYYY-MM-DD> --market zh-tw --currency TWD` |
| `抓这个链接后天台湾市场美元价格 <URL>` | 后天、台湾、美元 | `--date <后天YYYY-MM-DD> --market zh-tw --currency USD` |
| `2026-08-08 香港市场港币抓取 <URL>` | 指定日、香港、港币 | `--date 2026-08-08 --market zh-hk --currency HKD` |
| `抓取 /绝对路径/商品.xlsx` | 次日、台湾、台币 | `--input /绝对路径/商品.xlsx --date <次日> --market zh-tw --currency TWD` |
| `重跑刚才的商品，2026-08-08` | 仅覆盖日期 | 沿用已确认输入与市场/货币，覆盖 `--date 2026-08-08` |

相对日期必须以运行主机当前本地日期计算，不能使用对话创建日期或历史运行日期。若用户没有给出「刚才的商品」所指的、已确认的输入，则要求其重新提供 URL 或文件路径。

## 运行前检查

每一次执行前都检查，任一失败即停止，不循环重试：

1. `/System/Volumes/Data` 可用空间至少 2 GiB；不足时回复 `运行被阻止：数据卷可用空间不足 2 GiB`。
2. `/usr/local/bin/python3.14` 存在，且版本为 Python 3.14 或更新。
3. 在项目目录验证依赖：

   ```bash
   /usr/local/bin/python3.14 -c 'import openpyxl, playwright; print("runtime-ok")'
   ```

4. 已有登录中的 macOS 图形用户会话，且已安装 Edge 或 Chrome。
5. 为本次运行创建唯一的绝对结果目录：`/Users/tsimclaw/Documents/kkday-sku-price-scrape/<运行ID>`。

## 参数构造与命令

只从项目根目录执行。运行 API 能力允许重复传 `--url` 或 `--input`，但每一个值都要作为独立进程参数传递，不能把用户文本拼接到 shell 字符串。

```bash
cd /Users/tsimclaw/Develop/kkday_get_scoreandprice
RUN_ID="$(date +%Y%m%d_%H%M%S)"
RESULT_DIR="/Users/tsimclaw/Documents/kkday-sku-price-scrape/$RUN_ID"
/usr/local/bin/python3.14 kkday_get_scoreandprice.pyw \
  --url 'https://www.kkday.com/zh-tw/product/121004' \
  --date 2026-08-04 \
  --market zh-tw \
  --currency TWD \
  --launch-browser \
  --browser edge \
  --result-dir "$RESULT_DIR"
```

文件输入时以 `--input '/绝对路径/商品.txt'` 或 `--input '/绝对路径/商品.xlsx'` 替换或补充 `--url`。`--launch-browser` 是默认会话策略；只有项目专用浏览器已经准备好且 Agent 已知其本地 CDP HTTP 地址时，才使用 `--cdp-url http://127.0.0.1:<端口>`。**不可同时传入 --launch-browser 与 --cdp-url**。不得连接其他 Ctrip／Trip 工作流占用的端口。

## Hermes 远端执行方法

Hermes 必须从其配置的 `skills.external_dirs` 读取本项目的 `hermes-agent/skills` 目录；不得维护第二份全局 Skill。运行过程遵循下面的主机边界：

1. Hermes 网关若在 `tsimclaw` 的图形用户会话内触发，优先按上述命令使用 `--launch-browser` 和项目专用持久化 Edge 配置。
2. 若 Agent 实际处在纯 SSH shell，上述 Edge 可执行文件直接启动可能无法创建可用 CDP 会话。此时不要反复直接启动浏览器；一次性通过该 macOS 图形用户会话的 LaunchServices 启动**项目专用** Edge 配置，再仅附加该实例的 CDP HTTP 地址执行本项目命令。
3. 不得附加用户日常浏览器或默认浏览器 Profile；不得把临时 CDP WebSocket 标识写入日志、结果文件或回复。端口或浏览器实例不明确时停止并报告，而不是试探性连接。
4. 浏览器、登录和验证只允许一次正常启动／复用尝试。失败后按下一节交接给用户，不得后台循环拉起浏览器。

## 登录、风控与货币安全

- 不得读取、打印、导出、复制或修改 cookie、密码、授权头、CSRF token、OTP、会员标识或 DevTools WebSocket 标识。
- 不得自动填写凭据、绕过 CAPTCHA／DataDome／人机验证，或复制默认浏览器 Profile。
- 如果输出为 `auth_required`、`401`、`403`、挑战 HTML 或需要人工验证，停止并请用户在可见的项目专用浏览器中完成登录／验证；用户确认后只重新运行一次。
- 如果输出为 `currency_mismatch`，立即停止。不得换算、重标或交付这些价格；请用户先在可见 KKday 浏览器将会员币种切为本次 `--currency`，确认后只重新运行一次。
- 重新运行仍失败时，保留原生诊断产物并报告最终错误，不再提示登录或自动重试。

## 成功验收与交付

只在以下条件同时满足时宣布成功：进程退出码为 `0`；最终 JSON Lines `summary` 为 `failures: 0` 且至少有一个商品；`run_summary.json` 表示成功；`summary.output` 指向的 XLSX 位于本次结果目录；结果目录不存在 `failures.jsonl`。

| 退出码 | 含义 | Agent 动作 |
| --- | --- | --- |
| `0` | 完整成功 | 验证全部产物，再交付原生 `kkday_price_results.xlsx`。 |
| `2` | 参数或输入无效 | 只修正明确的路径／语法机械错误，最多重试一次；其余情况询问用户。 |
| `3` | 浏览器、会话、风控或运行时错误 | 不循环；按登录交接或报告阻塞原因处理。 |
| `4` | 部分商品失败或 `currency_mismatch` | 明确报告未完整成功，绝不声称价格已验证。 |

完整成功时，交付原生 XLSX，并说明使用日期、市场、请求货币、商品数、可信价格行数及结果目录。部分失败时，仅在文件存在时附上原生产物并标记「部分结果，不代表全部商品成功」，同时给出退出码和 `failures.jsonl` 路径。不得从日志重建、修复或猜测被标记为 `schema_unknown`、`missing_price`、`minimum_mismatch` 或其他不可信的价格。

## 禁止事项

不得在抓取请求中升级 Python 或安装依赖；不得修改源输入文件、活动浏览器 Profile 或 Hermes 网关虚拟环境；不得把输出目录或 XLSX 的存在当作成功证据；不得暴露任何会话数据。
