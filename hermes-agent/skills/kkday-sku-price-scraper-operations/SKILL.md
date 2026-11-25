---
name: kkday-sku-price-scraper-operations
description: 使用系统 Python 和 ego-browser task space 运行、恢复、验收 KKday SKU 价格抓取。
---

# KKday SKU 价格抓取操作

当用户要求抓取 KKday 商品价格、重跑任务、解释失败或交付 XLSX 时使用本 Skill。

## 硬约束

- 只使用系统 `python3 >= 3.11`，任何电脑上都不得使用 venv。
- ego-browser 是唯一浏览器运行时；必须复用命令指定的 task space。
- 不读取、输出或迁移 Cookie、密码、Token、验证码、会员标识和浏览器内部连接信息。
- 不规避 CAPTCHA/DataDome/MFA，不创建替代浏览器空间，不循环重试。
- 同一 task space 同时只允许一个批次。
- 任何登录/会话/401/OTP 处理先读 `~/.hermes/KKDAY_AUTH_GUIDE.md`；禁止按旧挑战恢复段打开 SCM 浏览器登录页或复制 cookie。公开商品可在游客上下文读取已验证商品接口，但这不证明 SCM 已登录。
- ego-browser v2.2.1 的 `page.evaluate` 若首参是表达式字符串，只接受单个参数；带业务参数时先用 JSON 序列化构造自调用表达式字符串。不要把 `page.evaluate(source, argument)` 的 fake-runner 测试通过当成真实兼容。
- 延迟加载页面可能有 `option-section` 却没有序列化的 `"pkg_oid"`；不得用缺少 pkg_oid 判定商品无套餐。检查真实商品资源图、经实际网络观察的套餐元数据接口和完整商品 ID 归属。只凭模拟 Nuxt fixture 或字符串断言通过，不能认定抓价修复成功；必须独立重跑原始 URL 并验证非零可信 SKU 及最终 XLSX。
- 连续修正后真实 canary 仍为 schema/0 trusted rows 时，保留失败证据并标明修复未完成；不要继续盲改、把测试通过当交付成功或发送空价格表冒充成果。

- 对首屏无套餐的商品，在同一次 ego-browser 调用内安装响应观察、打开原 URL 并等待正常 GET `fetch-packages-data` 返回。核对请求 `prodMid`、响应 `data['PRODUCT-SETTING'].prod_mid`、`PACKAGE` 与 `ITEM` 的逐级 ID；此响应仅证明套餐归属，不直接取价。不得因首屏出现 `option-section` 就提前结束等待。按日期在 SKU 接口与价格日历完成核验后，逐产品回读原生 XLSX。

## 固定抓取目标：Google Sheets 的 KKday 页签

- 用户指定的固定抓取表为 `https://docs.google.com/spreadsheets/d/1yTsSBTwLQN_dLKq08xpD1Set0sw9WptfQcewnkaA-cc/edit`。同一工作簿按平台分为 `Trip` 与 `KKday` 两个页签；KKday 固定入口为 `https://docs.google.com/spreadsheets/d/1yTsSBTwLQN_dLKq08xpD1Set0sw9WptfQcewnkaA-cc/edit?gid=1948158253#gid=1948158253`。
- KKday 任务只读 `KKday`（`gid=1948158253`），不得使用 `Trip`（`gid=0`）或未经校验的默认/活动工作表。可直接 HTTP 导出 `https://docs.google.com/spreadsheets/d/1yTsSBTwLQN_dLKq08xpD1Set0sw9WptfQcewnkaA-cc/export?format=xlsx&gid=1948158253`，验证页签及表头后生成 CLI 输入，无需为读表启动浏览器。
- 表头为 `eSIM | FR | USIMSA | JY | 富爾特 | TGT | TSIM`：`eSIM` 是目的地/区域分类，不是厂商或抓取 URL；其余六列为厂商，非空单元格为商品完整 URL。保留原 URL 的语言路径和 slug，从 `/product/<完整数字ID>` 提取商品 ID；空格/空单元格跳过，非空但非合法 KKday 商品链接须显式报错，不能静默漏抓。
- 保留每条输入的原行号、目的地、厂商、URL、商品ID。相同市场/币种下可按完整商品ID去重抓取，但必须保留并回填全部原始对应关系；同一商品可能出现在多个目的地行，不能把去重数当作表内目标格数，也不能丢掉第二处归属。
- 新批次先读取在线最新表，冻结本批次输入与来源（工作簿ID、页签名、gid、获取时间、文件哈希），再执行 canary/批量。断点恢复使用该批次冻结输入，不能重下在线表覆盖已有任务证据。在线读取失败时明确阻塞，不默用过期缓存；商品数量每批次动态核对，不写死历史统计。
- 用户说“KKday 固定抓取表/默认抓取目标/第二个页签”默认指此 `KKday` 页签；它与 Trip 抓取目标分开，不能覆盖 Trip 本地镜像或更改 Trip 定时任务。本规则只固化输入来源，不代表已创建 KKday 定时抓取任务。

## 运行前

日常参数直接使用 [`references/cli-quick-reference.md`](references/cli-quick-reference.md)。该页列出 `--date`、受支持市场、`--output` 与 `--result-dir` 的准确差异、单/多市场可复制命令，以及 2026-08-21 至 2026-10-21 的 `--help` 审计证据。只有源码/README 与该速查冲突或 CLI 报未知参数时才重新查询帮助。

```bash
python3 --version
python3 -c 'import openpyxl; print("runtime-ok")'
```

确认图形登录会话、输入、日期、市场、币种、结果目录和磁盘空间。先运行 1 商品 canary，再运行批次。

## 命令模板

```bash
python3 -m kkday_scraper.cli \
  --input '/absolute/path/products.txt' \
  --date 'YYYY-MM-DD' \
  --market zh-tw \
  --currency TWD \
  --ego-task-space 'kkday-batch-name' \
  --result-dir '/absolute/path/result'
```

## 挑战恢复

收到 `handoff_required` 时：

1. 读取事件中的 task space 名称/ID、原因、商品 URL 和 `agent_prompt`；
2. 复用同一个 task space，用 ego-browser 或 Computer Use 查看可见页面；
3. 只做等待、刷新一次、确认地区/语言、关闭普通提示框等正常交互；浏览器已自动填充账号密码时可点击一次登录；
4. CAPTCHA、MFA、账号选择、安全确认使用 `handOffTaskSpace` 交给真人；
5. 真人明确完成后再接管原空间、重新探测，并按相同命令重跑一次；
6. 再次失败即停止并交付部分结果和错误证据。

## Nuxt 页面结构兼容（2026-08 验证）

- 不要只将 `window.__NUXT__.pinia['option-section'].packages` 视为套餐存在的唯一证据。新版商品页可能不再把该 store 暴露到运行时 window，却仍在 Nuxt SSR 序列化 payload 中提供完整资源图。
- 页面探测应同时确认 SSR payload 中存在 `option-section` 与 `pkg_oid`。对商品 `528458`（`zh-hk`、HKD、2026-08-15）实测，资源图为 `PRODUCT.prodInfo.packages → PACKAGE.<pkg_oid>.items → ITEM.<item_oid>`；套餐 `1825449/2084045` 对应 item `1571226/1829822`。
- 兼容实现必须从 SSR payload 解码并按 URL 商品 ID 的 `prodInfo.packages` 过滤套餐，再读取 `PACKAGE.items`；不得从可见价格文案或按钮标签猜测 package/item ID。**DOM/SSR 仅用于资源 ID 与元数据，绝不可作为 SKU 价格来源。** 可信售价只可来自 `fetch-items-data → data[item].item.skus[].single_price.fullday`；日期可售性来自该接口 `calendar/closeList`，并必须与 `fetch-packages-price-calendar → min_price` 的套餐最低价交叉校验。结构漂移或不一致时失败关闭，不能以 DOM 补值。
- 验收：此商品应输出 HKD、119 个 `trusted` SKU 行、0 failures。项目测试固定使用 `python3 -m pytest -q`；不要用可能解析至用户目录旧包的 `uv run pytest`。
- **价格日历最低价的语义（2026-08-14 验证）**：`fetch-packages-price-calendar.min_price` 是套餐的全 SKU 展示最低价，可能属于在所选日期被 `fetch-items-data.closeList` 关闭的 SKU。可信售价仍只能取当日可售 SKU 的 `single_price.fullday`；一致性校验应确认 calendar 最低价存在于同套餐服务器 SKU 价格集合中，不能要求其等于可售 SKU 的最低价。若 calendar 最低价不在该价格集合，必须失败关闭。
- **无可售库存不等于价格错误**：整个套餐在所选日期没有可售 SKU 时，保留不可售业务结果/`no_available_sku`，不要误报 `price_mismatch` 或补造价格。
- **XLSX 行完整性**：每一条 SKU 行都必须保留 `厂商`、`商品ID`、`URL`、`商品名称`，不得只在同产品首行保留。ID、价格、评分和计数等所有数字字段必须按 Excel 文本写入。

## 币种门禁（2026-09-22 复核）

- 浏览器会员会话的实际结算币种由账号会话决定，不由 URL、`--market` 或偏好 cookie 决定。本机 ego-browser 会话当前实际返回 **HKD**。
- `--currency` 与探针返回币种不一致时，CLI 对每个商品写入 `currency_mismatch` 并以退出码 `4` 失败关闭。这是预期保护，不要绕过。
- 用户未指定币种、且 URL 为 `zh-tw` 时，若以默认 `TWD` 跑 canary 即得 `currency_mismatch`，应改以实际币种（HKD）重跑，并在交付说明中明确标注 HKD；**绝不可把 HKD 行标记为 TWD**。
- `~/Documents/KKdayScraper/preference_cookies.json` 不存在时，偏好 cookie 不参与币种决策；不要靠写该文件切换币种。

## 验收

- `0`：只有 requested=processed、failures=0、最终 XLSX 可读、摘要 final、无失败文件时才宣布完整成功；
- `3`：预检挑战，task space 已保留，等待恢复；
- `4`：部分结果或中途挑战，只能标为未完整成功；
- `2`：输入、参数、输出或运行时错误。

逐 URL 核对：每个 URL 都必须在 `抓取结果`、`失败商品` 或 `no_available_sku` 中出现。交付时说明日期、市场、币种、输入/处理/成功/失败数量、可信 SKU 行数、结果目录和 XLSX 路径。
