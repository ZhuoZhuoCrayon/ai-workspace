---
title: 工作区跨主机一键初始化
tags: [ai-workspace, bootstrap, skills, registry, portability]
description: 让 ai-workspace 在 macOS 或 Linux 主机克隆后，执行一次 make bootstrap 即可拉取项目仓库和私有仓库并挂载 skills
created: 2026-10-11
updated: 2026-10-11
---

# 工作区跨主机一键初始化

## 0x01 背景

### a. Why

工作区只能在当前主机上使用：入库文件写死了本机绝对路径，私有注册表 `private/repos.json` 没有入库，也没有按注册表重建项目和 skills 的命令。换一台主机克隆后，项目目录全部失效，`25` 个项目 skill 无法加载。

### b. 目标

- 新主机执行 `git clone` 和 `make bootstrap` 后即可使用工作区，内网仓库只在有权限时克隆。
- 入库文件不含主机相关路径，macOS 和 Linux 主机都能完成初始化。
- `make bootstrap` 可以重复执行，再次执行不会重复克隆。

## 0x02 实现路线

### a. 建议的方案

- 入库内容：只保留与主机无关的声明，即两份注册表、`skills-lock.json` 和自研 skills。
- 项目路径：`local_path` 改为相对 `PROJECTS_ROOT` 的路径，由 `project-mgr` 的注册表脚本统一解析。
- 私有数据：`private/` 拆为独立的内网私有仓库。
- 外部 skills：按 `skills-lock.json` 锁定的版本安装。
- 初始化入口：`make bootstrap` 按 `ai-workspace-private` 的 `git_url` 克隆 `private/`，再克隆缺失的项目仓库，安装 skills，在本机生成 IDE 目录的挂载链接。

### b. 约束

- skill 之间不互相引用，跨 skill 的流程只由 `Makefile` 编排。
- `make bootstrap` 不改用户目录。MCP 与 BKM CLI 的原生配置随私有仓库保存，换机时按 `configs/README.md` 复制到原路径。
- 初始化流程不改动已存在的仓库（包括私有仓库），拉取和提交都由使用者在对应仓库中执行。

## 0x03 参考

- 方案：[PLAN.md](./PLAN.md)
- 关联 issue：[Skills-First 架构演进](../2026-04-06-skills-first-architecture/README.md)
- 现有实现：`Makefile`、`CONTRIBUTING.md`、`.agents/skills/project-mgr/scripts/list_skills.py`
