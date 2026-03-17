# AI Workspace

## 0x01 初始化项目

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

## 0x02 更新 Skills

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
