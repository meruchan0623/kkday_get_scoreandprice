# Hermes 运行约束

1. 始终从项目根目录调用系统 `python3`；任何电脑上都不得使用 venv。
2. ego-browser 是唯一浏览器运行时。必须复用本次命令指定的 task space，不得启动其他浏览器会话、复制用户浏览器数据或读取凭据。
3. 执行前确认系统 Python 版本、`openpyxl` 导入、图形登录会话、输入 URL、日期、市场、币种、输出目录和可用磁盘空间。
4. 同一个 task space 只允许一个活动批次；所有浏览器操作串行执行。
5. 只允许向浏览器写入 `currency`、`country_lang`、`lang_ui` 三个非凭据偏好项。不得读取全量 Cookie。
6. 首先执行 1 商品 canary。canary 达到退出码 `0`、失败数 `0`、XLSX 可读后才执行批量任务。
7. 出现 `handoff_required` 时，复用事件中的 task space。可通过 ego-browser 或 Computer Use 做一次普通可见交互；若账号密码已经由浏览器自动填充，可点击一次登录。CAPTCHA、MFA、账号选择或安全确认必须移交真人。
8. 真人确认完成后才能接管原 task space，并以相同参数重跑一次。第二次仍失败则停止，不循环重试。
9. 逐 URL 验收：每个 URL 必须有可信价格行、明确失败或 `no_available_sku`。不得把其他商品的行数归给零行商品。
10. 完整成功必须同时满足：退出码 `0`、requested=processed、failures=0、final XLSX 可读、摘要为 final、无 `failures.jsonl`。否则只交付标明 partial 的结果和失败清单。
11. 抓取成功或部分成功时，交付给用户的是**程序原生输出 Excel（`kkday_price_results.xlsx` / `kkday_price_results.partial.xlsx` 的原始文件）**。不得用该原生 Excel 再次处理、转存、重导出或二次整理后再交付；直接把程序在磁盘上生成的原文件作为附件输出。
12. 单个任务可同时接受多个市场（如 zh-hk 与 zh-tw）的商品 URL；每个 URL 的 market 从路径自动识别，通过浏览器 market 请求头逐商品切换，**所有抓取目标合并进同一张「抓取结果」工作表输出**（每个 SKU 行记录其所属「市场」，两市场于同一原生 XLSX 交付），不再按市场拆分文件。`--market`/`--currency` 仍分别作为 URL 无 market 段时的回退值与全任务期望币种。

禁止披露 Cookie、密码、Authorization、CSRF、OTP、Token、会员标识、完整 HTML 或浏览器内部连接信息。不得规避 CAPTCHA/DataDome、安全机制或用户控制权。
