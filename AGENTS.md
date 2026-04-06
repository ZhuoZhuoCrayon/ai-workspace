# AI 工作区指引

本文件定义检索、操作与知识采信的硬约束。细节与编码风格见 `.cursor/rules/` 各专题文件。

## 0x01 强制规则

### a. RULE-LOCATE-001

消息中提到具体项目名时，第一步必须并行读取 `repos.json` 与 `private/repos.json`。
目标是获取项目的 `local_path`。
定位后优先检查 `<local_path>/AGENTS.md`。
先读取项目级规范，再执行后续动作。

### b. RULE-WD-001

涉及外部项目的 git 或文件操作时，必须在 `local_path` 目录执行。
禁止在 `ai-workspace` 根目录直接操作其他项目仓库。

### c. RULE-KNOWLEDGE-001

任何项目定位或知识检索，都必须并行读取公开与私有两条路径。
禁止只读取一侧后直接下结论。

### d. 知识与 Issue 管理规则

以下规则的完整定义见 `.agents/skills/knowledge_mgr/SKILL.md` § 0x05：

- **RULE-KNOWLEDGE-002**：知识检索优先级（会话 > 任务 > 知识库 > 项目规范 > 源码 > 通用 > 全局）
- **RULE-ISSUE-001**：Issue 目录仅含 `README.md` 与 `PLAN.md`
- **RULE-ISSUE-002**：迭代交付前主动询问 PLAN 写回
- **RULE-ISSUE-003**：Issue 文档职责分离（README 需求 vs PLAN 方案）
- **RULE-ISSUE-004**：PLAN 迭代采用主干融合 + 进展表格化

### e. RULE-PR-001

PR review 中可定位到文件与行号的问题，必须优先发布到对应代码位置。
禁止仅用 PR conversation 总结替代行级评论。

1. 可定位问题：使用行级 review comment（inline）发布到精确 `path:line`。
2. 总结性结论：发布到 PR conversation。
3. 仅当无法定位到单行或受工具限制时，才允许退化到 conversation；并且必须标注 `path:line` 与退化原因。

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
   更新时遵循 RULE-ISSUE-004：结论并入方案主干，进展写入表格。

## 0x04 冲突处理

- 优先级：任务直接要求 > 本文件 > 专项规则文件（`.cursor/rules/*.mdc`）> 引导入口（`CLAUDE.md` / `CODEX.md`）。
- 具体写法与检查项以 `.cursor/rules/*.mdc` 为准；与本文件冲突时仍以本文件为准。
