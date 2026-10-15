# AI Workspace

面向 Cursor / Codex / Claude 等 Coding Agent 的通用工作区模板，提供多仓项目注册、知识库索引、规则治理与技能体系，帮助团队把 AI 协作流程沉淀为可复用工程实践。

## 0x01 项目简介

AI Workspace 的目标是用“文件即协议”的方式，让人和 Agent 在同一套目录约定下协作：

- 项目定位：通过 `repos.json` / `private/repos.json` 管理多仓入口。
- 知识沉淀：通过 `knowledge/` / `private/knowledge/` 维护可检索知识库。
- 规则治理：通过 `.cursor/rules/` + `pre-commit` + CI 保证文档和流程质量。
- 能力扩展：通过 `.agents/skills/` 管理技能，初始化时挂载到各 IDE 目录。

## 0x02 快速开始

新机器需要 `git`、`make`、`uv`、`node`。有 nvm 时使用 `20.18.3`，没有则用 `PATH` 中的 `node`。克隆内网仓库还需要对应的访问凭据。

```bash
git clone https://github.com/ZhuoZhuoCrayon/ai-workspace.git
cd ai-workspace
make bootstrap
```

`make bootstrap` 依次做这几件事：

- 按 `repos.json` 中 `ai-workspace-private` 的地址把私有仓克隆到 `private/`。
- 把注册表中缺失的项目克隆到 `~/Project`。已有目录不拉取、不改动。
- 按 `skills-lock.json` 安装外部 skills，链接项目 skills，并把自研 skills 挂到 `.claude/skills/` 和 `.codebuddy/skills/`。
- 安装 `pre-commit` hook。

没有内网权限时，`private/` 和内网项目记为失败，其余继续。项目存放位置用 `PROJECTS_ROOT` 覆盖：

```bash
make bootstrap PROJECTS_ROOT=/data/workspace
```

MCP、Codex 和 BKM CLI 的配置不在这一步里。`private/` 克隆完成后，按 [private/configs/README.md](private/configs/README.md) 复制到用户目录。依赖、技能更新和提交检查见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 0x03 核心入口

- [AGENTS.md](AGENTS.md)：Agent 导航入口。
- `repos.json` / `private/repos.json`：项目注册表。
- `knowledge/` / `private/knowledge/`：项目知识库。
- `.agents/skills/`：工作区技能目录。
- `scripts/config/lint/` 与 `scripts/`：文档检查配置和脚本。

## 0x04 License

本项目采用 [MIT License](./LICENSE)。
