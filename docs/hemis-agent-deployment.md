# Hermes 自动化电脑部署与验收

## 前提

- macOS 图形用户会话已登录，ego lite/ego-browser 可在该会话中运行；
- 系统 `python3 >= 3.11`，并可导入 `openpyxl`；
- 不创建、不复制、不激活 venv；
- 有足够空间保存项目、运行日志和 XLSX；
- 不迁移浏览器凭据或用户浏览数据。

## 安装

将项目同步到固定目录并核对源码清单。不要传输结果目录、缓存、Cookie、密码或其他会话数据。使用系统 Python 安装项目声明的依赖；ego-browser 由 ego lite 提供，不由 pip 安装。

```bash
cd '/absolute/path/kkday_get_scoreandprice'
python3 --version
python3 -c 'import openpyxl; print("runtime-ok")'
python3 -m pip check
python3 -m pytest -q -m 'not live'
```

## Canary

在图形会话中以独立 task space 运行一个授权商品：

```bash
python3 -m kkday_scraper.cli \
  --url 'https://www.kkday.com/zh-tw/product/PRODUCT_ID-example' \
  --date 'YYYY-MM-DD' --market zh-tw --currency TWD \
  --ego-task-space 'kkday-hermes-canary' \
  --result-dir '/absolute/path/canary-result'
```

若输出 `handoff_required`，Hermes 复用同一个 task space，并通过 ego-browser 或 Computer Use 做普通可见交互。CAPTCHA、MFA、账号选择和安全确认交给真人；真人明确完成后按原命令重跑一次。不得自动 takeover、创建替代空间、规避挑战或无限重试。

Canary 必须同时满足退出码 `0`、失败数 `0`、最终 XLSX 可读、摘要为 final、无失败文件。否则部署仅完成代码/运行时检查，业务验收仍未通过。

## 20 商品批次

Canary 通过后使用输入文件运行批次，并为本次批次使用唯一 task space 和结果目录。逐 URL 核对 `抓取结果`、`失败商品` 和 `运行汇总`。完整成功要求输入数 20、处理数 20、失败数 0；否则交付 `.partial.xlsx` 和失败清单，明确说明不是完整成功。

回滚时回到迁移前的代码版本；新版本不会静默改用其他浏览器运行时。不要删除保留的 task space、诊断产物或结果文件，除非用户明确授权。
