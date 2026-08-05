# Hemis Agent 部署与验收

## 结论

这套程序可以部署到当前 Hemis/Hermes Agent 所在的 Mac mini，并由 Agent 通过 CLI 驱动，但当前主机不满足安全安装门禁。

已核实的适配条件：

- macOS 26.5，Apple Silicon arm64；
- 用户 `tsimclaw` 有正在运行的 GUI 会话；
- Microsoft Edge 与 Google Chrome 均已安装；
- Hermes Agent v0.18.2 正在通过 LaunchAgent 运行；
- Hermes 自身运行时包含 Python 3.11.15；主机另有官方系统级 Python 3.14.4。

当前阻塞条件：

- `/System/Volumes/Data` 仅约 651 MiB 可用；安装项目虚拟环境、Playwright Python 包、运行日志和浏览器 Profile 都可能耗尽磁盘；
- Apple 自带的 `/usr/bin/python3` 是 3.9.6，不满足项目 `>=3.11`；不得用它安装或运行；
- 项目尚未部署到远端固定路径，也尚未加入 Hermes 的 `skills.external_dirs`；
- KKday 专用浏览器 Profile 必须在远端机器上由用户完成首次登录/挑战验证，不能迁移或复制本机凭据。

因此，当前状态是“架构可部署，暂不应执行安装”。先释放空间，再按下列门禁部署。

## 目标布局

```text
/Users/tsimclaw/Develop/kkday_get_scoreandprice/
  HERMES.md
  kkday_get_scoreandprice.pyw
  kkday_scraper/
  hermes-agent/skills/kkday-sku-price-scraper-operations/SKILL.md

/Users/tsimclaw/Documents/kkday-sku-price-scrape/
  YYYYMMDD_HHMMSS/
```

浏览器 Profile 由程序放在：

```text
/Users/tsimclaw/Library/Application Support/KKdayScraper/browser-profiles/edge
```

## 部署事务

### 1. 空间与备份门禁

1. 只读分析磁盘占用并由用户确认清理项；不要自动删除 `Downloads`、Hermes 数据、浏览器 Profile 或现有抓取项目。
2. 清理后要求 `/System/Volumes/Data` 至少有 2 GiB 可用；建议 5 GiB 以上。
3. 若目标目录已存在，先读取 Git 状态或生成文件清单；禁止覆盖未提交或不明来源的远端改动。

### 2. 传输源码

从已验证的本地工作树生成明确文件清单并传输到：

```text
/Users/tsimclaw/Develop/kkday_get_scoreandprice
```

不要传输 `.git`、`__pycache__`、测试缓存、浏览器 Profile、结果目录或任何凭据。传输后对比源码清单/校验和。

### 3. 安装系统级 Python 运行时

使用官方系统级 Python `/usr/local/bin/python3.14`。不要创建项目虚拟环境；也不得向 `/Users/tsimclaw/.hermes/hermes-agent/venv` 安装项目依赖或让项目升级 Hermes 的包。

Apple 自带的 `/usr/bin/python3` 由系统保护，不能作为升级目标。Python 官方没有 LTS 分支；当前应使用官方最新稳定 Python 3.14 系列。若需要从 3.14.4 升级到更新的 3.14 补丁版，必须由具备 macOS 管理员授权的操作员安装 Python.org 签名的 macOS installer。

目标命令形态：

```bash
cd /Users/tsimclaw/Develop/kkday_get_scoreandprice
/usr/local/bin/python3.14 -m pip install --user --upgrade pip
/usr/local/bin/python3.14 -m pip install --user .
```

本项目连接系统已安装的 Edge/Chrome，不需要执行 `playwright install chromium` 下载额外浏览器。如 Playwright 版本确实要求辅助组件，先重新核对磁盘余量再安装。

### 4. 配置 Agent 发现

把以下目录加入 Hermes 配置的 `skills.external_dirs`：

```text
/Users/tsimclaw/Develop/kkday_get_scoreandprice/hermes-agent/skills
```

不得复制到 `~/.hermes/skills/`。修改前备份实际 Hermes 配置文件，修改后使用 Hermes 自带的配置读取/技能列表命令证明 Skill 已被发现；不要只凭文件存在判断成功。若配置变更需要重启 gateway，应先记录当前 PID/状态，并在重启后验证 LaunchAgent、日志和现有 Agent 功能。

### 5. 本地验收

```bash
cd /Users/tsimclaw/Develop/kkday_get_scoreandprice
/usr/local/bin/python3.14 --version
/usr/local/bin/python3.14 -c 'import openpyxl, playwright; print("runtime-ok")'
/usr/local/bin/python3.14 -m compileall -q kkday_scraper kkday_get_scoreandprice.pyw
/usr/local/bin/python3.14 kkday_get_scoreandprice.pyw --help
```

The CLI defaults are next local calendar day, `zh-tw`, and `TWD`. The Hermes project Skill must translate natural-language overrides into `--date`, `--market`, and `--currency`; it must not silently use the current day. A `currency_mismatch` result is a failed run, not a conversion request.

若部署测试依赖，再运行：

```bash
/usr/local/bin/python3.14 -m pytest -q -m 'not live'
```

### 6. 浏览器与首次人工登录

先用一个明确、低风险的 KKday 商品 URL 做单商品 smoke test。Agent 启动专用 Edge 后，用户在远端 Mac 的可见窗口中完成登录或挑战验证。Agent 不读取或代填凭据。

用户确认后重新执行一次 smoke test。验收必须同时满足：退出码 `0`、最终 `summary.failures=0`、`run_summary.json` 成功、工作簿存在、无 `failures.jsonl`。

### 7. 回滚

- Skill 配置失败：恢复 Hermes 配置备份并验证 gateway 回到原状态。
- 项目运行失败：停止使用项目目录，不删除浏览器 Profile或诊断产物。
- 新部署不接管端口、不替换现有 `trip-score-price-scraper`，两者的结果目录和 Agent Skill 名称必须保持独立。

## 不允许的部署方式

- 在磁盘低于门禁时“先装了再说”；
- 使用系统 Python 3.9；
- 把依赖装进 Hermes gateway 的虚拟环境；
- 复制任何浏览器默认 Profile、Cookie、密码或 DevTools WebSocket 地址；
- 与现有 Trip/Ctrip 抓取器共用固定调试端口；
- 只看到 Excel 文件就宣称部署或抓取成功；
- 未验收 Skill 发现、进程退出码和真实单商品运行就设置定时任务。
