---
title: 外部仓库 Git 操作在沙箱中静默失败
tags: [cursor, sandbox, git, external-repo]
description: 对工作区外部仓库执行 git 命令时，沙箱写权限限制导致命令静默失败（exit 1 + 空输出）
created: 2026-02-18
updated: 2026-02-18
---

# 外部仓库 Git 操作在沙箱中静默失败

## 0x01 关键信息

### a. 现象

通过 `repos.json` 中 `local_path` 定位到工作区外部的仓库（如 `/Users/xxx/Project/Tencent/bkm/skills`），执行 `git status`、`git diff --cached`、`git commit` 等命令时：

- exit code = 1
- stdout 和 stderr 均为空
- 无任何错误提示

### b. 环境

- Cursor IDE Agent 模式
- Shell 工具默认沙箱：写权限限于工作区目录，外部路径只读
- 外部仓库的 `.git/` 目录位于沙箱写权限范围之外

### c. 根因

沙箱文件系统限制：git 命令在执行过程中需要读写 `.git/` 目录（如 lock 文件、index 等），当仓库位于工作区外部时，沙箱拒绝写操作，git 以 exit 1 静默退出且不输出错误信息。

## 0x02 排查过程

1. 默认沙箱执行 `git status` → exit 1 + 空输出
2. 加 `required_permissions: ["all"]` 但直接用 `cd && git` → 仍失败（shell 状态问题）
3. 用 `bash -c 'cd /path && git status 2>&1'` + `required_permissions: ["all"]` → 成功

## 0x03 解决方案

对工作区外部仓库执行 git 操作时，**必须**同时满足两个条件：

1. **请求 `all` 权限**：`required_permissions: ["all"]` 禁用沙箱
2. **使用 `bash -c` 包裹**：确保 `cd` 和 git 命令在同一子 shell 中执行

```bash
# ✅ 正确写法
bash -c 'cd /path/to/external/repo && git status 2>&1'

# ❌ 错误写法（即使有 all 权限，shell 状态可能不持久）
cd /path/to/external/repo && git status
```

**快速模板**：

```bash
# 查看状态
bash -c 'cd <local_path> && git status --porcelain 2>&1'

# 查看暂存
bash -c 'cd <local_path> && git diff --cached --name-status -M 2>&1'

# 提交
bash -c 'cd <local_path> && git commit -m "message" 2>&1'
```

## 0x04 参考

- Cursor Shell 工具沙箱文档：写权限限于工作区目录，`required_permissions: ["all"]` 可完全禁用
- `AGENTS.md`：外部项目通过 `repos.json` 的 `local_path` 定位
