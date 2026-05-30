# AI Workspace

面向 Cursor / Codex / Claude 等 Coding Agent 的通用工作区模板，提供多仓项目注册、知识库索引、规则治理与技能体系，帮助团队把 AI 协作流程沉淀为可复用工程实践。

## 0x01 项目简介

AI Workspace 的目标是用“文件即协议”的方式，让人和 Agent 在同一套目录约定下协作：

- 项目定位：通过 `repos.json` / `private/repos.json` 管理多仓入口。
- 知识沉淀：通过 `knowledge/` / `private/knowledge/` 维护可检索知识库。
- 规则治理：通过 `.cursor/rules/` + `pre-commit` + CI 保证文档和流程质量。
- 能力扩展：通过 `.agents/skills/` 与 `.cursor/skills/` 统一管理技能。

## 0x02 快速开始

初始化工作区：

```bash
make init
```

更多贡献流程、依赖安装、提交前检查和技能更新方式见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 0x03 核心入口

- [AGENTS.md](AGENTS.md)：Agent 导航入口。
- `repos.json` / `private/repos.json`：项目注册表。
- `knowledge/` / `private/knowledge/`：项目知识库。
- `.agents/skills/`：工作区技能目录。
- `config/lint/` 与 `scripts/`：文档检查配置和脚本。

## 0x04 License

本项目采用 [MIT License](./LICENSE)。
