---
name: git-workflow
description: Git 提交规范。用户要求提交、commit、拆分提交、起草 commit message、整理待提交范围或处理暂存区时必须使用。用于区分工作区知识库提交与非工作区项目提交：默认按工作区规范，用户明确要求提交其他项目时遵循项目自身规范。
---

# Git 提交规范

## 0x01 场景判断

先判断提交对象：

- 如果用户明确要求提交非工作区（知识库）的项目变更，按 `0x02` 处理。
- 否则按工作区（知识库）变更提交处理，使用 `0x03` 的规范。

不要因为变更路径看起来像某个项目，就自动切换到项目提交规范。

## 0x02 非工作区项目提交

进入目标项目后，遵循项目自身规范：

- 先读取项目 `AGENTS.md`。
- 查找并读取贡献者文档，例如 `CONTRIBUTING.md`。
- 查看项目提交历史，再起草分组方案和 commit message。
- 项目规范与工作区规范冲突时，以项目规范为准。

## 0x03 工作区知识库提交

Commit message 遵循 Conventional Commits：`<type>(<scope>): <subject>`。

Scope 使用工作区约定：`knowledge`、`skill`、`project`、`issue`、`rules`。

- 当用户说“提交工作区变更”时，默认按变更主题拆分多个 commit，而不是合并成一个 commit。
- 分类优先按“为什么要改”分组，例如：`docs/rules`、`feat/skill`、`ci/tooling`、`chore/workspace`。
- 工作区内存在来自不同会话的改动时，默认先确认范围，用户明确要求一起提交时可继续分类提交。
- 提交前先查看 `git status`、`git diff HEAD` 和 `git log`，再起草分组方案和 commit message。
- 同一 commit 只保留一个明确主题，避免把规则、脚本、知识文档和配置混在一起。
- 单组改动不足以独立提交时，可并入最接近主题的一组，但不能跨主题硬拼。

## 0x04 输出约定

- 实际提交后说明 commit hash 与 message。
- 仅起草方案时输出分组方案与 commit message 草案。
