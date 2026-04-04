---
title: 文档规范检查工具替代调研
tags: [ai-workspace, docs, tooling, lint]
description: 调研成熟文档检查工具是否可替代 scripts/check_doc_style.py
created: 2026-04-04
updated: 2026-04-04
---

# 文档规范检查工具替代调研

## 0x01 背景

### a. Why

当前工作区通过 `scripts/check_doc_style.py` 维护 Markdown / MDC 文档规范。该脚本以自研规则为主，维护成本和扩展成本会随规则数量上升。

需要评估是否存在成熟工具可直接替代或部分替代现有脚本，以降低维护负担并提升规则生态兼容性。

### b. 目标

- 盘点可用于文档规范检查的成熟工具（开源或商业均可）。
- 评估这些工具对当前规则集的覆盖能力、可配置能力和落地成本。
- 给出三类结论之一：完全替代、混合方案（工具 + 少量自定义脚本）、继续维持现状。

## 0x02 实现路线

### a. 建议的方案

1. 梳理 `scripts/check_doc_style.py` 的规则清单，按能力域分类（命名、结构、格式、语言、frontmatter）。
2. 选择候选工具并做对照评估，重点关注：
   - 规则覆盖率
   - 可扩展机制（插件、正则、自定义规则）
   - 与 pre-commit / CI 的集成成本
   - 与现有仓库结构（`knowledge/`、`private/knowledge/`、`.cursor/rules/`）的兼容性
3. 输出迁移建议与 PoC 结论（含实施步骤、风险、回滚策略）。

### b. 约束

- 不影响现有 pre-commit 的稳定性与执行时长。
- 不降低现有关键规则约束力度（如标题层级、编号格式、frontmatter 合法性）。
- 方案需兼容多模型协作场景（Cursor / Codex / Claude）。

## 0x03 参考

- 现有脚本：`scripts/check_doc_style.py`
- 现有 Hook：`.pre-commit-config.yaml`
