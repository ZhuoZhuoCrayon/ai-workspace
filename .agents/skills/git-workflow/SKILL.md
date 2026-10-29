---
name: git-workflow
description: >
  Git 提交规范。
  用户要求提交、commit、拆分提交、起草 commit message、整理待提交范围或处理暂存区时必须使用。
  用户要求交付 PR 或 MR 时也必须使用：交付完成后按 code-review 把评审建议发到该 PR 或 MR，并处理到可合并。
  用于区分工作区知识库提交与非工作区项目提交：默认按工作区规范，用户明确要求提交其他项目时遵循项目自身规范。
  有 `.gtm.yaml` 时不因本节改走普通 Git 交付，建单、提交、推送和创建 PR 仍用 GTM CLI。
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

项目接入 PreCI 时，提交前执行 [PreCI 配置准备](../gtm-cli-delivery/SKILL.md#e-worktree-的-preci-准备)。

## 0x03 工作区知识库提交

Commit message 遵循 Conventional Commits：`<type>(<scope>): <subject>`。

Scope 使用工作区约定：`knowledge`、`skill`、`project`、`issue`、`rules`。

- 当用户说“提交工作区变更”时，同时检查工作区根目录和 `private/`。根目录的改动按本段提交；`private/` 有改动时按 `0x04` 提交。两边都有改动就各提一次。
- 本机和开发机都会推送同一条主干。提交前用 rebase 把当前分支接到远端，再创建新提交。
- 工作区不干净且 rebase 会改到这些文件时，先暂存改动，完成后再恢复。
- 这次同步不新增 merge commit。

```bash
git fetch origin
git rebase origin/main
```

分叉时改为：

```bash
git pull --rebase origin main
```
- 默认按变更主题拆分多个 commit，而不是合并成一个 commit。
- 分类优先按“为什么要改”分组，例如：`docs/rules`、`feat/skill`、`ci/tooling`、`chore/workspace`。
- 工作区内存在来自不同会话的改动时，默认先确认范围，用户明确要求一起提交时可继续分类提交。
- 提交前先查看 `git status`、`git diff HEAD` 和 `git log`，再起草分组方案和 commit message。
- 同一 commit 只保留一个明确主题，避免把规则、脚本、知识文档和配置混在一起。
- 单组改动不足以独立提交时，可并入最接近主题的一组，但不能跨主题硬拼。

## 0x04 私有仓库提交

`private/` 是独立的私有仓库，地址只记录在 `private/repos.json`。工作区 `.gitignore` 排除了它，根目录的 `git status` 看不到这里的文件。

用户说“提交工作区变更”，或明确要求提交 `private/` 时，在 `private/` 内执行：

```bash
git status
git diff HEAD
git log
```

提交前按 `0x03` 同步主干。私有仓主干是 `master`。

```bash
git fetch origin
git rebase origin/master
```

`make private-pull` 只做快进。不能快进时用上面的 rebase，再执行：

```bash
make private-push
```

按 `0x03` 的 Conventional Commits 和分组规则提交。作者使用该仓库已配置的 `user.name` 与 `user.email`。

```bash
git add <paths>
git commit -m "<type>(<scope>): <subject>"
```

提交后推送。另一台机器拉取：

```bash
make private-push
make private-pull
```

不要把 `private/` 的文件放进工作区暂存区。`private/` 没有自己的 `AGENTS.md`，不另读项目规范。

## 0x05 交付后的评审

用户要求交付 PR 或 MR 时，先完成目标项目自己的交付路径，再执行本节。

PR 或 MR 回读成功后：

1. 按 code-review 审查这张 PR 或 MR。
2. 把本次 review 建议发布到这张 PR 或 MR。
3. 能在本任务里修复的问题留在同一分支修复，按原来的交付路径提交，然后重新审查。
4. 达到可合并后停止。用户没有要求合并时，不合并。

| 条件 | 要求 |
| --- | --- |
| 阻塞问题 | 没有未修复的 P0、P1 |
| 冲突 | 与目标分支无冲突 |
| 检查 | [a] 必需检查没有失败<br />[b] 排队或运行中的检查保留原状态 |
| 线程 | 本轮已确认修复的线程已 resolve |
| 草稿 | PR 或 MR 处于可评审状态 |

没有未修复的 P0、P1 时提交通过评审。GitHub 的 approve body 为 `LGTM`。工蜂执行 `gongfeng review approve`。平台拒绝作者自审时停止重试，并说明剩余阻塞。

P2 不阻止可合并，随评审一起发布。

## 0x06 输出约定

- 实际提交后说明 commit hash 与 message。
- 仅起草方案时输出分组方案与 commit message 草案。
