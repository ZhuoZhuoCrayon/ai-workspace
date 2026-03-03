---
title: 优化 bk-ci-helper — 实施方案
tags: [bkm-skills, bk-ci-helper, optimization]
issue: knowledge/bkm-skills/issues/2026-03-01-ci-helper-best-practices/README.md
description: 分 4 步将 bk-rpc-inspection 最佳实践迁移到 bk-ci-helper
created: 2026-03-01
updated: 2026-03-01
---

# 优化 bk-ci-helper — 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 方案概述

逐项对照 `bk-rpc-inspection/SKILL.md` 对应章节，将改进合并到 `bk-ci-helper/SKILL.md`，保持原有业务逻辑不变。

## 0x02 实施步骤

### Step 1：脚本 Python 3.6 兼容性检查

1. 检查 `scripts/` 下 3 个脚本的 type hints（`dict[str, ...]` → `Dict[str, ...]`）、walrus operator、match-case 等 3.10+ 语法
2. 修复不兼容写法，确保 `python3.6 -c "import ast; ast.parse(open('script.py').read())"` 通过

### Step 2：升级脚本执行 / 路径解析（0x02.b）

替换 `SKILL.md` 的「脚本执行」章节：

1. **symlink 路径解析**：`os.path.realpath` 4 步流程（解析 Skill 目录 → 脚本路径 → bk-data-fetcher 路径 → 验证）
2. **执行规则**：绝对路径 + 禁止 `python3 -c` 内联 + `working_directory` 执行模式
3. **MCPClient 调用规范**：独立 `.py` 脚本 + `bkmonitor-files/` 输出约定

源：`bk-rpc-inspection/SKILL.md` 0x02.b 完整章节

### Step 3：强化文件流 + 辅助脚本驱动式排查（0x02.c）

增强排查规范，补充：

1. 确认查询参数准确的前提下，数据可**并行查询**再分析
2. **CRITICAL：禁止通过人工阅读 JSON 归纳分布模式**，必须编写辅助脚本定量统计
3. `--output` 参数统一以 `bkmonitor-files/` 为前缀

源：`bk-rpc-inspection/SKILL.md` 0x02.c

### Step 4：升级报告输出规范（0x05）

替换 `SKILL.md` 的 0x05 章节：

1. **避免遗忘策略**：数据收集阶段禁止提前阅读格式文件，报告输出阶段再按场景完整阅读
2. **输出闸门（5 项自检）**：已确定场景 → 已确定格式 → 已完成全部步骤 → 已按顺序阅读必读文件 → 已满足唯一组合约束
3. 保留原有 `common_format.md` / `output_format.md` / `notification_format.md` 三文件结构

源：`bk-rpc-inspection/SKILL.md` 0x05

## 0x03 验证

- [ ] `find` 被 `os.path.realpath` 替代，symlink 场景路径正确
- [ ] 3 个脚本通过 Python 3.6 语法检查
- [ ] 报告输出闸门覆盖所有案例（告警分析、流水线运行、系统指标）

---
*制定日期：2026-03-01*
