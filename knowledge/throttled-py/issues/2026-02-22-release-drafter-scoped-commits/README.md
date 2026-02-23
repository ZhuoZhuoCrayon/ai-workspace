---
title: Release Drafter 支持 scoped conventional commits
tags: [ci, release-drafter, dependabot]
description: 让 autolabeler 正确匹配 build(deps) 等带 scope 的提交标题
created: 2026-02-22
updated: 2026-02-22
---

# Release Drafter 支持 scoped conventional commits

## 0x01 背景

项目通过 `.github/release-drafter-config.yml` 自动生成 Release Notes。Dependabot PR 标题为 `build(deps): bump urllib3 from 2.5.0 to 2.6.3`，当前 autolabeler 正则 `/^build: .*/` 不支持带 scope 的格式，导致这类 PR 无法被打上 `kind/build` 标签，不会出现在「📦 Dependencies」分类中。同理，`feat(core): ...`、`fix(store): ...` 等也不会被匹配。

**目标**：autolabeler 正则兼容 `type(scope): description` 格式，不影响现有无 scope 格式的匹配。

## 0x02 实现路线

修改 `autolabeler` 的 9 条 title 正则，scope 部分改为可选匹配。

以 `build` 为例：`/^build: .*/` → `/^build(\\([^)]+\\))?: .*/`

**约束**：仅修改 `release-drafter-config.yml`，不涉及 workflow 文件。开发分支：`ci/260222_release_log`。

## 0x03 参考

- `.github/release-drafter-config.yml`
- [Conventional Commits](https://www.conventionalcommits.org/) | [Release Drafter autolabeler](https://github.com/release-drafter/release-drafter#autolabeler)
