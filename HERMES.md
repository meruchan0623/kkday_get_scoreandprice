# Hemis / Hermes Agent 项目入口

本文件是 Hemis Agent 驱动本项目时的唯一入口。执行 KKday SKU 价格抓取、诊断、重试或交付结果前，必须完整读取：

`hermes-agent/skills/kkday-sku-price-scraper-operations/SKILL.md`

主机必须通过 Hermes 配置的 `skills.external_dirs` 加载上述项目内 Skill。不要把 Skill 复制到 `~/.hermes/skills/`，也不要使用同名的全局旧副本。

项目只允许 Agent 使用根目录入口 `kkday_get_scoreandprice.pyw` 的 CLI 模式。无参数 GUI 仅供人工操作，不是 Agent 调度入口。

## Hermes 标准操作流程

Hermes 必须按以下顺序执行，不能跳过运行前检查或产物验收：

1. **解析请求**：确认每个 KKday 商品 URL 或绝对输入文件路径；明确使用日期、市场和币种。用户未指定时，使用运行主机的下一个自然日、`zh-tw` 和 `TWD`，并把默认值显式写入命令。
2. **确认运行环境**：确认当前主机、项目根目录和项目内 Skill 指定的解释器；检查 `/System/Volumes/Data` 至少有 2 GiB 可用空间，验证 `openpyxl`、`playwright` 可导入，并确认 macOS 图形用户会话和 Edge/Chrome 可用。不得临时安装依赖、创建虚拟环境或改用复制脚本。
3. **创建独立结果目录**：每次运行使用唯一绝对目录 `/Users/tsimclaw/Documents/kkday-sku-price-scrape/<运行ID>`，不得覆盖其他批次或修改源 TXT/XLSX。
4. **启动专用浏览器并切换分站**：默认传 `--launch-browser --browser edge`，仅使用 `KKdayScraper/browser-profiles` 下的专用 Profile。每次会员预检前，CLI 会先导航到 `--market` 对应的分站首页（`zh-tw` 或 `zh-hk`），再读取会话状态；这样复用浏览器时不会沿用上一批次的商品分站。`BrowserSession.connect()` 在新建页面前会自动注入持久化的站点偏好 Cookie（见下节“币种 Cookie 自动注入”），使会员接口回读目标币种。只有端口和实例归属明确时才可改用 `--cdp-url`；不得连接用户日常浏览器、猜测端口、复制默认 Profile 或输出 DevTools WebSocket 标识。
5. **执行一次批次抓取**：从项目根目录调用 `kkday_get_scoreandprice.pyw`；多个 URL 分别重复传入 `--url`，不要拼成一段未转义的 shell 文本。记录完整 JSON Lines 和进程退出码。
6. **按状态分流**：`401`、`403`、挑战页、验证码、MFA 或用户接管浏览器时交还用户；`currency_mismatch` 时先确认持久化币种 Cookie 存在且为目标币种（见下节），必要时通过浏览器 UI 切换并回读。不得绕过挑战、读取会话凭据、换算价格或无限重试。用户完成必要操作并确认后，最多复用同一专用会话重跑一次。
7. **逐 URL 验收**：检查每个请求 URL 是否出现在 `可售SKU`、`失败与警告` 或明确的无可售结果说明中。`product_count` 等于输入数并不代表每个商品都有价格；某 URL 为零行且无失败时，应报告“指定日期无可售 SKU”，不能把其他商品的行数归给它。
8. **完整成功验收**：进程退出码必须为 `0`，最终 `summary.failures` 必须为 `0`，`run_summary.json` 必须为 `status: final`，`summary.output` 指向的 XLSX 必须可读，结果目录不得存在 `failures.jsonl`。交付时说明日期、市场、币种、输入商品数、每个 URL 的可信行数和结果目录。

浏览器已打开、会员接口 HTTP 200、`product_count` 正确或 XLSX 已生成都只是中间证据，任何单项都不能替代逐 URL 与最终产物验收。详细参数、退出码和交接规则以项目内 Skill 为准。

## 币种 Cookie 自动注入（首选）与 UI 切换（兜底）

分站域名与会话币种是两个独立状态：`--market` 只控制进入哪个分站首页，不能保证会员状态接口返回 `--currency` 指定的币种。项目通过持久化的**站点偏好 Cookie**在 CDP 连接时自动设置币种，正常情况下无需任何 UI 操作。`currency_mismatch` 的处理顺序如下。

### 首选：持久化偏好 Cookie 自动注入

- 存储位置：`~/Documents/KKdayScraper/preference_cookies.json`，文件权限 `0600`。放在 Documents 下便于在 Hermes 自动化机上定位和备份，且不受浏览器 Profile 重置影响。
- 由 `kkday_scraper/cookie_store.py` 管理，白名单只允许三个非凭据站点偏好：`currency`、`country_lang`、`lang_ui`。session、CSRF、`KKWEB`、`datadome` 等凭据一律不写入，尝试写入会被拒绝。
- `BrowserSession.connect()` 通过 CDP 连接专用浏览器后、新建页面前，自动调用 `context.add_cookies()` 注入这些偏好 Cookie；随后导航到分站首页并由 `probe_member` 回读币种。
- Cookie 保留原始 host-only domain（如 `www.kkday.com`，不加前导点），才能覆盖浏览器 Profile 中已有的同名 host-only 币种 Cookie。
- 当 `currency_mismatch` 出现时，先确认该文件存在且 `currency` 值等于目标币种；若缺失或错误，按明确的市场和币种参数重新生成后重跑。

直接从本次明确的市场和币种参数生成白名单偏好项。禁止调用浏览器全量 Cookie API，禁止先读取登录 Cookie 再过滤：

```bash
python3 - <<'PY'
from kkday_scraper.cookie_store import save_preference_cookies

market = "zh-tw"
currency = "TWD"
save_preference_cookies([
    {"name": "currency", "value": currency, "domain": "www.kkday.com", "path": "/", "secure": True, "httpOnly": True, "sameSite": "Lax"},
    {"name": "country_lang", "value": market, "domain": "www.kkday.com", "path": "/", "secure": True, "httpOnly": True, "sameSite": "Lax"},
    {"name": "lang_ui", "value": market, "domain": "www.kkday.com", "path": "/", "secure": True, "httpOnly": True, "sameSite": "Lax"},
])
PY
```

将示例参数替换为本次 `--market` 与 `--currency`；domain 固定为 host-only `www.kkday.com`。验证：写入后 `load_preference_cookies()` 能读到三项，且专用浏览器注入后 `get-member-status` 返回的 `currency` 等于目标币种。

### 兜底：UI 切换（仅当 Cookie 注入未生效）

当持久化 Cookie 正确但会员接口仍返回其他币种（例如服务端忽略 Cookie 而依据 IP/账户偏好），且用户已明确指定目标币种并授权切换时，Hermes 才使用 Computer Use 在**当前可见的项目专用 Edge/Chrome 窗口**中修改 KKday 币种偏好。

1. **确认操作边界**：只操作本次 CLI 启动或复用的 `KKdayScraper/browser-profiles` 专用浏览器窗口。不得操作用户日常浏览器、默认 Profile 或不明归属的窗口。
2. **读取当前 UI 状态**：使用 Computer Use 的 `get_app_state` 读取目标浏览器最新可访问性树；若币种菜单、账户区或页面主体无法可靠识别，再读取截图。不要复用上一次状态的 `element_index`、坐标或菜单编号。
3. **进入目标分站**：在可见专用窗口访问本次 `--market` 对应首页，等待页面加载完成。
4. **定位并打开币种控件**：优先用可访问性文本定位当前币种、货币、地区或语言/币种菜单；语义控件不足时用最新截图做一次可见点击。每次点击、滚动或输入后都必须重新读取状态。控件选择器参考：`button.header__currency` 打开币种弹层，弹层中的 `.currency` 选项以 `TWD 新臺幣` 等文案标识目标币种。
5. **选择目标币种**：仅选择用户已经明确授权的三字母币种。不要填写账户、密码、验证码、OTP、卡号或其他敏感信息。
6. **回写偏好 Cookie**：UI 切换成功后，按上节方法仅从已明确参数重新生成 `preference_cookies.json`，使后续批次无需再次手动切换。
7. **人工交接条件**：若出现登录、账户选择、验证码、MFA、人机验证、浏览器安全警告、权限请求，或用户已接管浏览器，立即停止并交还用户。
8. **接口回读验证**：UI 显示切换成功并不充分。必须重新执行一次本项目 CLI 预检/抓取，并确认会员状态接口返回币种与 `--currency` 完全一致后，才能开始或重跑商品抓取。
9. **重跑限制**：用户完成切换并确认后，复用同一个专用浏览器会话最多重跑一次。若仍出现 `currency_mismatch`，保留诊断产物并报告会话币种未生效。

UI 操作不允许读取、打印、复制、导出或持久化 session、Authorization、CSRF、密码、OTP、会员标识或 DevTools WebSocket 标识（唯一例外是上面白名单内的三个站点偏好 Cookie，且只能通过 `cookie_store` 写入其专用文件）。最终币种真值以 CLI 的会员状态接口响应为准，而不是 UI 文案、URL 或分站域名。
