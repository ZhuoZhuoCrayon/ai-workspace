# 贡献指南

本文件说明如何初始化 AI Workspace、准备必要依赖、更新技能目录，以及在提交前运行检查。

## 0x01 前置依赖

开始前确认本机具备以下工具：

- `git`：用于拉取仓库和提交变更。
- `make`：用于执行项目封装命令。
- `uv`：用于运行 Python 开发依赖和 `pre-commit`。
- `nvm`、`node`、`npm` / `npx`：用于安装 skills 和运行 Markdown 检查依赖。

默认 Node.js 版本由 `Makefile` 的 `NODE_VERSION` 控制，目前为 `20.18.3`。

如果你的 `nvm` 安装路径不是 `$HOME/.nvm/nvm.sh`，执行命令时覆盖 `NVM_SCRIPT`。

## 0x02 初始化项目

直接执行：

```bash
make bootstrap
```

默认行为：

- 克隆缺失的 `private/` 和注册项目，已有目录保持不动。
- 按 `skills-lock.json` 安装外部 skills。
- 链接项目 skills，并把自研 skills 挂到 `.claude/skills/` 和 `.codebuddy/skills/`。
- 安装 git `pre-commit` hook。

`make bootstrap` 还会安装 GitHub CLI。尚未登录 github.com 且当前是交互终端时，接着执行 `gh auth login`。没有交互终端时只打印登录命令。

登录凭据留在 GitHub CLI 的凭据存储里，不进仓库。

`PROJECTS_ROOT` 覆盖项目存放根目录，默认 `~/Project`。私有仓库的改动在 `private/` 里提交：先 `git -C private pull --ff-only`，再执行 `make repos-sync` 补齐新登记的项目。

`make bootstrap` 不处理这些本机内容：

- `~/.cursor/mcp.json`、`~/.codex/config.toml`、`~/.codebuddy/mcp.json`。
- `~/.bkm-cli/` 下的 profile 和集群配置。
- `~/.git-credentials` 和用户目录下的 skills。

Agent 与 BKM CLI 的配置在 `private/configs/`，换机时按 `private/configs/README.md` 复制回原路径。

常用覆盖参数：

```bash
make bootstrap NODE_VERSION=20.18.3 UV=uv
make bootstrap PROJECTS_ROOT=/data/workspace
```

参数说明：

- `NODE_VERSION=20.18.3`：本机有 nvm 时切换到这个版本；没有 nvm 时使用 `PATH` 中的 `node`。
- `UV=uv`：Python 工具入口，默认读取 `pyproject.toml` 中的镜像源配置。

## 0x03 更新 Skills

更新工作区内的外部 skills，并重新链接项目 skills：

```bash
make skills-update
```

维护者确认差异后提交 `skills-lock.json`。`-p` 只更新安装在工作区内的 skills。

将 `.agents/skills/` 里的目录挂到 IDE 目录：

```bash
make skills-mount
```

挂载目标由 `SKILLS_MOUNT_TARGETS` 控制，默认是 `.claude` 和 `.codebuddy`。项目 skills 是符号链接，不挂到 IDE 目录。Cursor 直接读取 `.agents/skills/`。

如需跳过部分 skill，可以覆盖 `SKILLS_MOUNT_BLACKLIST`。

## 0x04 提交前检查

提交前建议执行：

```bash
make verify
uv run pre-commit run
```

检查内容：

- `make verify`：确认 `pre-commit` 可用、git hook 已安装，并检查 skill 链接和来源。
- `uv run pre-commit run`：检查当前暂存文件。

当前 `pre-commit` 包含以下检查：

- `lint-md`
- `markdownlint-cli2`
- `check-doc-style`

也可以先确认 hook 已安装，再执行正常 `git commit`。

`pre-commit` 会自动检查暂存文件。
