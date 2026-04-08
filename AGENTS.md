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

以下规则入口与摘要见 `.agents/skills/knowledge_mgr/SKILL.md` 的 `0x03 规则锚点`。

### e. 规则与 Skill 治理

- **RULE-GOVERN-001**：错误预防、行为规范类规则，必须写入对应方向的 skill 或 rule 文件，禁止堆积到 `AGENTS.md`。本文件仅保留全局结构性约束与导航。
- **RULE-GOVERN-002**：`.cursor/rules/*.mdc` 是过渡态，所有 rules 最终都应演进为 skills（agent-agnostic、可迁移）。当某条 rule 新增内容时，主动提醒用户是否启动向 skill 的迁移。演进路线见 `knowledge/ai-workspace/issues/2026-04-06-skills-first-architecture/PLAN.md`。
- **RULE-GOVERN-003**：skill 新增或修改前，必须先读取 skill-creator 规范并严格审查。

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

规则读取策略（通用）：

1. 按任务场景读取对应规则文件（按需读取，不预加载全部规则）。
2. 进入具体任务前，优先读取 `0x02 快速入口` 中对应专题规则。
3. 专题规则更新时，以 `0x02 快速入口` 表格中的对应规则路径为准；`AGENTS.md` 保持导航职责。

## 0x03 Issue 处理流程

1. 阅读 `knowledge/<project>/issues/<YYYY-MM-DD-title>/README.md`。
2. 并行检索 `knowledge/<project>/` 与 `private/knowledge/<project>/`，并阅读 `<local_path>/AGENTS.md`。
3. 制定 `knowledge/<project>/issues/<YYYY-MM-DD-title>/PLAN.md`。
4. 按 PLAN 执行。
5. 将实施进展、阶段结论与后续动作更新到同目录 `PLAN.md`。
   更新时遵循 RULE-ISSUE-004：先更新受影响的方案主干片段，再写入实施进展表格。

## 0x04 冲突处理

- 优先级：任务直接要求 > 本文件 > 专项规则文件（以 `0x02 快速入口` 表格中的路径为准）> 引导入口（`CLAUDE.md` / `CODEX.md`）。
- 具体写法与检查项以对应专题规则文件为准；与本文件冲突时仍以本文件为准。
