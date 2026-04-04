# AI Workspace

面向 Cursor / Codex / Claude 等 Coding Agent 的通用工作区模板，提供多仓项目注册、知识库索引、规则治理与技能体系，帮助团队把 AI 协作流程沉淀为可复用工程实践。

## 0x01 项目简介

AI Workspace 的目标是用“文件即协议”的方式，让人和 Agent 在同一套目录约定下协作：

- 项目定位：通过 `repos.json` / `private/repos.json` 管理多仓入口。
- 知识沉淀：通过 `knowledge/` / `private/knowledge/` 维护可检索知识库。
- 规则治理：通过 `.cursor/rules/` + `pre-commit` + CI 保证文档和流程质量。
- 能力扩展：通过 `.agents/skills/` 与 `.cursor/skills/` 统一管理技能。

## 0x02 初始化项目

直接执行：

```bash
make init
```

默认行为：

- 安装 `pre-commit` hook。
- 安装默认 skills 到 `Cursor` 对应的 `.agents/skills/`。

默认 skills：

- `skill-creator`
- `mcp-builder`
- `docx`
- `pdf`
- `pptx`
- `xlsx`
- `webapp-testing`

可选参数：

```bash
make init SKILLS_IDE=cursor
make init SKILLS_IDE=
make init NODE_VERSION=20.18.3 PRE_COMMIT_PYENV_VERSION=3.10.4
```

说明：

- `SKILLS_IDE=cursor`：默认值，仅安装到 `Cursor`。
- `SKILLS_IDE=`：留空时不传 `--agent`，按 `skills` CLI 默认行为执行。

## 0x03 更新 Skills

直接执行：

```bash
make skills-update
```

只更新部分 skills：

```bash
make skills-update SKILLS="skill-creator mcp-builder"
```

如需调整目标 IDE，也可以临时覆盖：

```bash
make skills-update SKILLS_IDE=cursor
```

## 0x04 License

本项目采用 [MIT License](./LICENSE)。
