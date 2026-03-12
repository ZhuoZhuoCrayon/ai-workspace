---
title: 告警日志查询支持 Doris 数据源
tags: [log, unify-query, doris, data-source]
description: 根因在 UnifyQuery 的 Doris 字段转换，_index 应映射为 *，bkmonitor 无需改动
created: 2026-03-12
updated: 2026-03-12
---

# 告警日志查询支持 Doris 数据源

## 0x01 背景

### a. Why

Doris 不支持使用 `_index` 字段。最初判断是 `bkmonitor` 侧在构建 UnifyQuery 参数时需要做字段映射。

### b. 目标

定位告警日志查询在 Doris 场景的真实责任边界，明确是否需要在 `bkmonitor` 侧修改。

## 0x02 实现路线

### a. 建议的方案

在 UnifyQuery 侧修复 Doris 字段转换逻辑：`_index` 在 Doris 查询应映射为 `*`，而不是 `NULL`。

### b. 约束

- 本问题归因于 UnifyQuery 的 Doris 适配层，不属于 `bkmonitor` 数据源映射逻辑
- `bkmonitor` 侧相关改动已回滚，不再推进该方向实现

### c. 结论

- 根因：UnifyQuery Doris 维度转换中，`_index` 未按预期转换为 `*`，导致下游出现 `NULL`
- 处置：在 UnifyQuery 修复；`bkmonitor` 无需改动
- 状态：本需求在 `bkmonitor` 侧关闭（跟踪 UQ 侧修复结果）

## 0x03 参考

- 关联需求：`knowledge/bkmonitor/issues/2026-02-10-log-ds-to-unify-query/README.md`
