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

### d. RULE-KNOWLEDGE-002

回答项目问题或执行项目任务时，按以下优先级检索并采信：

1. 会话上下文
2. 任务上下文 → `knowledge/<project>/issues/<YYYY-MM-DD-title>/`
3. 项目知识库 → `knowledge/<project>/` + `private/knowledge/<project>/`（含 issues / snippets / troubleshooting）
4. 项目自身规范 → `<local_path>/AGENTS.md`、`<local_path>/.cursor/rules/`
5. 项目源码 → `<local_path>`（仅 1–4 未命中时）
6. 通用知识 → `knowledge/_shared/` + `private/knowledge/_shared/`
7. 工作区全局 → `AGENTS.md`、`.cursor/rules/`、`.agents/skills/`、`.cursor/skills/`

### e. RULE-ISSUE-001

Issue 目录只使用 `README.md` 与 `PLAN.md` 两个文件。  
任务进展统一写回 `PLAN.md`。  
不创建 `PROGRESS.md`。

### f. RULE-ISSUE-002

基于 issue 的迭代在出现实质变更后，交付前必须主动询问是否同步 `PLAN.md`。  

1. 实质变更包括代码、文档或配置修改。  
2. 询问使用固定句式：`是否需要我将本轮进展与关键结论同步到该 issue 的 PLAN.md？`  
3. 若用户明确拒绝，可跳过本次写回。

### g. RULE-ISSUE-003

Issue 文档职责必须分离，禁止混写。  

1. `README.md` 只记录需求定义与方法论，不记录调研细节、对比表、星标快照、语法样例结论。  
2. `PLAN.md` 承载调研结论、语法模式对比、实现路径、验收与进展。  
3. 在 `README.md` 中允许出现“调研对象列表”（例如主流库名单），但不得展开为结论性内容。  
4. 若发现 `README.md` 混入调研细节，必须先回收至 `PLAN.md` 再继续后续工作。

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
