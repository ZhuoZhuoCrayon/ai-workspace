---
title: 告警日志查询支持 Doris 数据源 —— 实施方案
tags: [log, unify-query, doris, data-source]
issue: knowledge/bkmonitor/issues/2026-03-12-log-query-doris-support/README.md
description: 结论更新为 UQ 侧修复 _index 到 *，bkmonitor 侧不实施改动
created: 2026-03-12
updated: 2026-03-12
---

# 告警日志查询支持 Doris 数据源 —— 实施方案

> 基于 `knowledge/bkmonitor/issues/2026-03-12-log-query-doris-support/README.md` 更新。

## 0x01 调研结论

- 该问题不在 `bkmonitor` 的 `LogSearchTimeSeriesDataSource` 实现层
- 真实问题在 UnifyQuery Doris 侧：`_index` 应转换为 `*`，当前被转换为 `NULL`

## 0x02 处理决策

- 决策：由 UnifyQuery 修复 Doris 字段转换逻辑
- `bkmonitor` 侧动作：不改代码，维持现状
- 已执行：回滚此前 `bkmonitor` 侧针对该问题的实验性提交

## 0x03 跟踪与验证

- 在 UQ 修复后，验证 Doris 场景下告警日志查询不再出现 `NULL` 导致的异常
- 验证口径：同一查询在 ES 与 Doris 路径下均可正常返回

## 0x04 参考

- 关联 issue：`knowledge/bkmonitor/issues/2026-03-12-log-query-doris-support/README.md`
- 历史关联：`knowledge/bkmonitor/issues/2026-02-10-log-ds-to-unify-query/README.md`

---
*更新日期：2026-03-12*
