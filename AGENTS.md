# AI 工作区指引

本文件定义检索、操作与知识采信的硬约束。细节与编码风格见 `.cursor/rules/` 各专题文件。

## 0x01 强制规则

- `RULE-LOCATE-001`：消息中提到具体项目名时，第一步必须并行读取 `repos.json` + `private/repos.json` 获取 `local_path`；定位后优先检查 `<local_path>/AGENTS.md` 获取项目级规范。
- `RULE-WD-001`：涉及外部项目的 git / 文件操作，必须在 `local_path` 目录执行，禁止在 `ai-workspace` 根目录直接操作其他项目仓库。
- `RULE-KNOWLEDGE-001`：任何项目定位或知识检索，必须并行读取公开 + 私有两条路径，禁止只读一侧后下结论。
- `RULE-KNOWLEDGE-002`：回答项目问题或执行项目任务时，按以下优先级检索并采信：
  1. 会话上下文
  2. 任务上下文 → `knowledge/<project>/issues/<YYYY-MM-DD-title>/`
  3. 项目知识库 → `knowledge/<project>/` + `private/knowledge/<project>/`（含 issues / snippets / troubleshooting）
  4. 项目自身规范 → `<local_path>/AGENTS.md`、`<local_path>/.cursor/rules/`
  5. 项目源码 → `<local_path>`（仅 1–4 未命中时）
  6. 通用知识 → `knowledge/_shared/` + `private/knowledge/_shared/`
  7. 工作区全局 → `AGENTS.md`、`.cursor/rules/`、`.agents/skills/`、`.cursor/skills/`
- `RULE-ISSUE-001`：Issue 目录只使用 `README.md` + `PLAN.md` 两文件；任务进展写回 `PLAN.md`，不创建 `PROGRESS.md`。

## 0x02 快速入口

| 目标 | 路径 | 说明 |
|------|------|------|
| 通用规范 | `.cursor/rules/general.mdc` | 语言、路径、输出偏好 |
| 文档规范 | `.cursor/rules/markdown.mdc` | Markdown 结构和写作要求 |
| Git 规范 | `.cursor/rules/git.mdc` | Conventional Commits 与提交策略 |
| PR Review | `.cursor/rules/pr-review.mdc` | PR 复查流程与评论规范 |
| Python 规范 | `.cursor/rules/python-type-annotations.mdc` | 类型标注与风格 |
| Go 规范 | `.cursor/rules/go-dev.mdc` | Go 开发环境与 gvm |
| 项目注册表 | `repos.json` + `private/repos.json` | 并行读取获取 `local_path` |
| 知识入口 | `knowledge/INDEX.md` + `private/knowledge/INDEX.md` | 并行读取后按项目下钻 |
| 工作区 Skills | `.agents/skills/` | 通用技能 |
| Cursor Skills | `.cursor/skills/` | Cursor 兼容技能目录 |

## 0x03 Issue 处理流程

1. 阅读 `knowledge/<project>/issues/<YYYY-MM-DD-title>/README.md`。
2. 并行检索 `knowledge/<project>/` 与 `private/knowledge/<project>/`，并阅读 `<local_path>/AGENTS.md`。
3. 制定 `knowledge/<project>/issues/<YYYY-MM-DD-title>/PLAN.md`。
4. 按 PLAN 执行。
5. 将实施进展、阶段结论与后续动作更新到同目录 `PLAN.md`。

## 0x04 冲突处理

- 优先级：任务直接要求 > 本文件 > 专项规则文件（`.cursor/rules/*.mdc`）> 引导入口（`CLAUDE.md` / `CODEX.md`）。
- 具体写法与检查项以 `.cursor/rules/*.mdc` 为准；与本文件冲突时仍以本文件为准。
