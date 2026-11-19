# KKday 价格 CLI 速查

固定仓库：

```bash
cd /Users/tsimclaw/Develop/kkday_get_scoreandprice
```

使用系统 `python3 >= 3.11`，不使用 venv。日常请求直接套用下列参数，不为确认市场、日期或输出目录无条件运行 `--help`。

## 参数合同

| 参数 | 可用值/含义 |
|---|---|
| `--url URL` | 单个商品；可重复 |
| `--input PATH` | `.txt` 或 `.xlsx`；可重复 |
| `--date YYYY-MM-DD` | 使用日期；省略时按任务实际启动时的 Asia/Shanghai 下一个自然日。业务任务应显式传入 |
| `--market` | `zh-tw, zh-hk, ja-jp, ja, zh-cn, en`；是 URL 无受支持市场段时的回退值 |
| `--currency CODE` | 三位英文字母的期望币种，不换算；默认 `TWD` |
| `--ego-task-space NAME` | 复用同一个 ego-browser task space |
| `--output DIR` | 输出根目录，程序创建独立时间戳运行目录 |
| `--result-dir DIR` | 精确结果目录，不再创建时间戳子目录，并对目录加锁 |

`--output` 与 `--result-dir` 都可被解析；日常自动化/可重跑任务优先显式使用 `--result-dir`。输入至少包含一个 `--url` 或 `--input`。

## 可复制命令

### 单商品，精确结果目录

```bash
python3 -m kkday_scraper.cli \
  --url 'https://www.kkday.com/zh-hk/product/<PRODUCT_ID>-<slug>' \
  --date 'YYYY-MM-DD' \
  --market zh-hk \
  --currency HKD \
  --ego-task-space 'kkday-<batch-name>' \
  --result-dir '/absolute/path/result'
```

### TXT/XLSX 批次

```bash
python3 -m kkday_scraper.cli \
  --input '/absolute/path/products.xlsx' \
  --date 'YYYY-MM-DD' \
  --market zh-tw \
  --currency HKD \
  --ego-task-space 'kkday-<batch-name>' \
  --result-dir '/absolute/path/result'
```

含市场段的 URL 按自身市场抓取；混合市场 URL 可在同一任务中合并到一个原生 `kkday_price_results.xlsx`，`--market` 仅作回退。`--currency` 是整个任务的期望币种；浏览器会话返回不同币种时应以 `currency_mismatch` 失败关闭，不改标签冒充期望币种。

### 让程序创建时间戳目录

```bash
python3 -m kkday_scraper.cli \
  --url 'https://www.kkday.com/zh-tw/product/<PRODUCT_ID>-<slug>' \
  --date 'YYYY-MM-DD' \
  --market zh-tw \
  --currency TWD \
  --ego-task-space 'kkday-<batch-name>' \
  --output '/absolute/path/output-root'
```

## 历史 `--help` 证据（2026-08-21 至 2026-10-21）

按完全相同的 `date + command` 去除重放后，KKday CLI 有 22 条原始 `--help` 记录、15 个唯一调用，另有 7 条重放重复。唯一调用中，4 个是明确查参数/独立帮助，8 个只是运行前环境与 CLI 就绪检查，3 个是开发测试链验证。

- 市场参数反复查询：`77695/77899`（重放一组）、`78101`、`78323`。
- 明确查参数/独立帮助：市场参数三次（上项）以及 `92878`。
- 运行前就绪检查：`106328`、`107103/107321`、`109261/110102`、`110259/110647`、`110818/110956`、`113412/113595`、`113726`、`117544`；这些与日期、Python、依赖、磁盘或进程检查串联，不宣称为真实求助。
- 构建/开发验证而非真实求助：`80425`、`80502/80592`、`81498`（均与 pytest/compileall 等串联）。

这些证据说明最常缺的是市场、日期默认值和 `--output`/`--result-dir` 的区别，因此本页正向给出可复制命令，不把所有出现 `--help` 的记录都算成求助。
