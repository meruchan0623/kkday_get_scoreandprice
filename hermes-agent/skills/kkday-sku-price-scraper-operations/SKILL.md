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

## 运行前

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
