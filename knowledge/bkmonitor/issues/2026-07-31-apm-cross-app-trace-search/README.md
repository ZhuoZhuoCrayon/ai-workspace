---
title: APM 跨应用 Trace 检索
tags: [apm, trace, cross-app-search, index-set, bklog, celery, unify-query]
description: 通过 Trace 数据源域索引集聚合同域 APM Trace 数据源，让 Trace Detail 返回跨应用 Span
created: 2026-07-31
updated: 2026-07-31
---

# APM 跨应用 Trace 检索

## 0x01 背景

### a. Why

APM Trace 当前按应用维护结果表和日志索引集。用户按 Trace ID 检索前必须先确定应用，无法直接找到同业务内跨应用传播的完整调用链。

BKLog 已支持一个索引集关联多个结果表，并通过 DataLabel 交给 UnifyQuery 查询。APM 可以按 Trace 数据源域维护聚合索引集，复用现有 Trace 数据源。

### b. 目标

- 白名单 Trace 数据源域的 Trace Detail 可以按 Trace ID 检索同域全部 APM 应用。
- Trace 数据源域索引集随应用创建、删除自动收敛，并由周期任务修复遗漏。
- 同一索引集支持成员使用不同的 `storage_cluster_id`。

## 0x02 实现路线

### a. 建议的方案

- 索引集名称由 `bk_biz_id` 唯一确定，负数 ID 规范化为 `bkapm_cross_trace_space_{abs(bk_biz_id)}`，BKMonitor 不保存 `index_set_id` 映射。
- Celery 同步任务实时读取 APM 应用、Trace 数据源和 ES 存储配置，再查询 BKLog 索引集：未命中时创建，命中且有成员时按 ID 更新，无成员时删除。
- 应用创建完成、删除完成时触发 Trace 数据源域对账；周期任务扫描白名单并复用同一对账入口。
- Trace Detail 后台每次无缓存查询 BKLog 索引集，根据实时 `index_set_id` 构造 DataLabel 并查询 UnifyQuery。

### b. 约束

- 能力默认关闭，仅对白名单 Trace 数据源域生效。
- Trace 数据源域索引集与现有应用级索引集并存，不修改应用级索引集生命周期。
- 每个索引成员显式携带自己的 `storage_cluster_id`，索引集级配置只作兼容兜底。
- 任一成员缺少结果表或存储信息时终止本轮更新，避免写入不完整快照。
- 本期只适配 Trace Detail 后台接口，不修改 APM Web 前端和其他 Trace 查询接口。
- Trace 数据源域退出白名单后立即关闭跨应用查询，遗留的 BKLog 索引集暂不清理。

## 0x03 参考

- [实施方案](./PLAN.md)
- [APM 支持跨应用共享数据源](../2026-03-03-apm-shared-datasource/README.md)
- [日志数据源切换 unify-query](../2026-02-10-log-ds-to-unify-query/README.md)
- [优化首页 TraceID 全局搜索的预计算延迟](../2026-05-02-overview-trace-id-low-latency-search/README.md)
