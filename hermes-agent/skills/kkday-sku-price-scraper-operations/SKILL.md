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

## 验收

- `0`：只有 requested=processed、failures=0、最终 XLSX 可读、摘要 final、无失败文件时才宣布完整成功；
- `3`：预检挑战，task space 已保留，等待恢复；
- `4`：部分结果或中途挑战，只能标为未完整成功；
- `2`：输入、参数、输出或运行时错误。

逐 URL 核对：每个 URL 都必须在 `抓取结果`、`失败商品` 或 `no_available_sku` 中出现。交付时说明日期、市场、币种、输入/处理/成功/失败数量、可信 SKU 行数、结果目录和 XLSX 路径。
