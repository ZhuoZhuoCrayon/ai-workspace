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
make init
```

默认行为：

- 安装 git `pre-commit` hook。
- 安装默认 skills 到当前配置的目标 IDE。

常用覆盖参数：

```bash
make init SKILLS_IDE=cursor
make init SKILLS_IDE=
make init NODE_VERSION=20.18.3 UV=uv
```

参数说明：

- `SKILLS_IDE=cursor`：默认值，仅安装到 Cursor。
- `SKILLS_IDE=`：留空时不传 `--agent`，按 skills CLI 默认行为执行。
- `NODE_VERSION=20.18.3`：切换安装 skills 时使用的 Node.js 版本。
- `UV=uv`：Python 工具入口，默认读取 `pyproject.toml` 中的镜像源配置。

## 0x03 更新 Skills

更新默认 skills：

```bash
make skills-update
```

只更新部分 skills：

```bash
make skills-update SKILLS="<skill-a> <skill-b>"
```

调整目标 IDE：

```bash
make skills-update SKILLS_IDE=cursor
```

将 `.agents/skills/` 挂载到本地 Agent 目录：

```bash
make skills-mount
```

默认挂载目标由 `SKILLS_MOUNT_TARGETS` 控制。

`repos.json` / `private/repos.json` 中声明的项目 skills 会自动加入 ignore，不挂到 Agent 目录。

如需跳过部分 skill，可以覆盖 `SKILLS_MOUNT_BLACKLIST`。

## 0x04 提交前检查

提交前建议执行：

```bash
make verify
uv run pre-commit run
```

检查内容：

- `make verify`：确认 `pre-commit` 可用、git hook 已安装，并检查 skills 目录存在。
- `uv run pre-commit run`：检查当前暂存文件。

当前 `pre-commit` 包含以下检查：

- `lint-md`
- `markdownlint-cli2`
- `check-doc-style`

也可以先确认 hook 已安装，再执行正常 `git commit`。

`pre-commit` 会自动检查暂存文件。
