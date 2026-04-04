---
title: 优化 bk-ci-helper — 引入 bk-rpc-inspection 最佳实践
tags: [bkm-skills, bk-ci-helper, optimization, best-practices]
description: 将 bk-rpc-inspection 中验证有效的工程实践迁移到 bk-ci-helper，提升脚本兼容性、路径健壮性、排查规范和报告质量
created: 2026-03-01
updated: 2026-03-01
---

# 优化 bk-ci-helper — 引入 bk-rpc-inspection 最佳实践

## 0x01 背景

### a. Why

`bk-rpc-inspection` 在 `bk-ci-helper` 基础上做了多项工程实践升级（Python 3.6 兼容、symlink 路径解析、脚本驱动式排查规范、报告输出闸门机制等），这些改进已在实战中验证有效，应反向回馈到 `bk-ci-helper`。

### b. 现状对比


| #   | 能力         | bk-ci-helper 现状              | bk-rpc-inspection 实践                                                |
| --- | ---------- | ---------------------------- | ------------------------------------------------------------------- |
| 1   | Python 兼容性 | 未明确约束                        | 3.6 兼容（`Dict`/`List` 替代内建泛型、无 walrus/match-case）                    |
| 2   | 路径解析       | `find . -name "<script>"` 定位 | `os.path.realpath` 解析 symlink → 缓存绝对路径                              |
| 3   | 脚本执行       | 仅要求绝对路径                      | 绝对路径 + 禁止 `python3 -c` 内联 + `working_directory` 模式 + MCPClient 调用规范 |
| 4   | 排查规范       | 基础文件流 + grep/tail            | 并行查询 + 定量统计 + **CRITICAL** 禁止人工阅读 JSON 归纳                           |
| 5   | 报告输出       | 直接引用格式文件                     | 分阶段策略（数据阶段禁读格式文件）+ 输出闸门 5 项自检                                       |


### c. 目标

将上述 5 项 Gap 补齐，仅迁移通用工程实践，不涉及 RPC 业务逻辑。

## 0x02 约束

- 保持 bk-ci-helper 现有章节结构（0x01~0x05），在原位增强
- 脚本改动需验证对现有 `fetch_events.py` / `analyze_events.py` / `fetch_metrics.py` 的兼容性

## 0x03 参考

- 源：`skills/bk-rpc-inspection/SKILL.md`（0x02.b、0x02.c、0x02.d、0x05）
- 目标：`skills/bk-ci-helper/SKILL.md`
