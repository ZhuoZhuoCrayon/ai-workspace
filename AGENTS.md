# AI 工作区导航

本文件是 Agent 统一入口，只承担根目录导航职责。

具体任务规则见 `.agents/skills/`，按场景读取，不预加载全量目录。

## 0x01 项目说明

- AI Workspace 是面向 Cursor / Codex / Claude 等 Coding Agent 的通用工作区模板。
- 根目录文档只保留入口信息，领域规则由 `.agents/skills/` 承载。
- `AGENTS.md` 是唯一 Agent 引导入口。

## 0x02 常用入口

| 场景 | 入口 |
| --- | --- |
| 了解项目 | `README.md` |
| 初始化、依赖与提交检查 | `CONTRIBUTING.md` |
| 读取任务规则 | `.agents/skills/` |
| 查看检查配置 | `scripts/config/lint/` |
| 查看辅助脚本 | `scripts/` |
