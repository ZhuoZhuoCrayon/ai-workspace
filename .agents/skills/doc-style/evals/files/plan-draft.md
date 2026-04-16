# 实施方案草稿

- 我们要做一个 `doc-style` skill。
- 它主要是从 `markdown.mdc` 迁移过来。
- 还要更新 `AGENTS.md`、`general.mdc`，再删掉旧规则。
- 交付前要做 `quick_validate`、触发评测和质量评测。
- skill 里面要写通用写法、`README` 写法、`PLAN` 写法、`snippet` 和 `troubleshooting` 的写法。
- 还要保证 `knowledge_mgr` 仍然管 knowledge 资产，不要让 `doc-style` 抢走 frontmatter 或索引的职责。

- 开发上会涉及 skill 目录、`references/`、`evals/`，还有知识库里的 Skills-First `PLAN`。
- 验证上至少得跑 `quick_validate`、`lint-md`、`markdownlint-cli2`、`check_doc_style.py`。
- 最好还能做触发评测。

- 风险可能是 skill 太长。
- 风险也可能是触发不稳定、和 `knowledge_mgr` 职责重叠、旧入口丢失。
- 现在这份草稿还没有章节，也没有表格。
