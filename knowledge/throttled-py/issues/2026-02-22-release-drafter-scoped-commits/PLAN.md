---
title: Release Drafter 支持 scoped conventional commits —— 实施方案
tags: [ci, release-drafter, dependabot]
issue: knowledge/throttled-py/issues/2026-02-22-release-drafter-scoped-commits/README.md
description: autolabeler 正则修改方案与逐条变更清单
created: 2026-02-22
updated: 2026-02-22
---

# Release Drafter 支持 scoped conventional commits —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 现状

autolabeler 9 条 title 规则均使用 `/^{type}: .*/` 格式，不支持 `feat(xxx)`、`build(deps)` 等符合 `{type}({scope})` 的模式。2 条 body 规则不受影响。

## 0x02 方案

将 9 条 title 正则统一改为 `/^{type}(\\([^)]+\\))?: .*/`，scope 部分可选。

以 `build` 为例：`/^build: .*/` → `/^build(\\([^)]+\\))?: .*/`

- `([^)]+)` 而非 `(.*)`：scope 仅匹配非 `)` 字符且至少一个字符，避免贪婪匹配越界和空括号 `()`
- YAML 中括号需双重转义：正则 `\(` → YAML `\\(`

## 0x03 实施步骤

1. 在 `ci/260222_release_log` 分支修改 `.github/release-drafter-config.yml` 的 autolabeler 部分
2. 提交：`ci: support scoped conventional commits in release-drafter autolabeler`
3. 推送分支，创建 PR 到 `main`

---
*制定日期：2026-02-22*
