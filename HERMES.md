# Hemis / Hermes Agent 项目入口

本文件是 Hemis Agent 驱动本项目时的唯一入口。执行 KKday SKU 价格抓取、诊断、重试或交付结果前，必须完整读取：

`hermes-agent/skills/kkday-sku-price-scraper-operations/SKILL.md`

主机必须通过 Hermes 配置的 `skills.external_dirs` 加载上述项目内 Skill。不要把 Skill 复制到 `~/.hermes/skills/`，也不要使用同名的全局旧副本。

项目只允许 Agent 使用根目录入口 `kkday_get_scoreandprice.pyw` 的 CLI 模式。无参数 GUI 仅供人工操作，不是 Agent 调度入口。

