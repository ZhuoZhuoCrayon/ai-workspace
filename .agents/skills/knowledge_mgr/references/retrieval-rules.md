# Retrieval Rules

只在需要确认稳定检索规则原文时阅读本文件。

触发判定与排除条件见 [SKILL.md](../SKILL.md) 的 `0x00 触发与排除`，本文件不重复定义。

## 0x01 RULE-KNOWLEDGE-002 — 知识检索优先级

回答项目问题、执行项目任务或出现知识目录检索行为时，按以下优先级检索并采信：

1. 会话上下文
2. 任务上下文 → `knowledge/<project>/issues/<YYYY-MM-DD-title>/`
3. 项目知识库 → `knowledge/<project>/` + `private/knowledge/<project>/`
4. 项目自身规范 → `<local_path>/AGENTS.md`
5. 项目源码 → `<local_path>`（仅 1-4 证据不足时）
6. 通用知识 → `knowledge/_shared/` + `private/knowledge/_shared/`
7. 工作区全局指导 → `AGENTS.md`、当前任务相关的工作区规范入口

补充要求：

- 除会话上下文外，涉及知识目录的层级都默认并行检查 `knowledge/` 与 `private/knowledge/`。
- 命中 `snippet` / `troubleshooting` 且知识内容足以回答用户时，优先直接交付文档中的代码块或排障流程；路径仅作为证据，不应成为主要输出。
- 只有当前层证据不足时，才进入下一层。
- **【CRITICAL（必须执行不可协商）】进入源码前，应明确说明知识未命中或知识冲突的原因。**
