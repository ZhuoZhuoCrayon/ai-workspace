---
title: APM Span 内置指标支持声明式引用
tags: [apm, span, metric-group, trace, unify-query, declarative]
description: 将 Trace 概览图的 Span 指标查询从手工参数拼接收敛为可复用的声明式指标算子
created: 2026-05-07
updated: 2026-05-07
---

# APM Span 内置指标支持声明式引用

## 0x01 背景

### a. 问题

`apm_web.trace.resources.TraceChatsResource.perform_request` 当前直接拼接大量图表查询参数。

这些参数同时承载指标语义、UnifyQuery 查询结构和前端图表兼容字段，导致新增或调整 Span 指标时容易重复改写多份 dict。

### b. 现有基础

项目已经通过 `QueryConfigBuilder`、`UnifyQuerySet` 和 `BaseMetricGroup` 提供声明式查询能力。

`ResourceMetricGroup` 与 `TrpcMetricGroup` 已经证明该模式可以沉淀为可复用指标算子。

## 0x02 目标

- 新增 APM Span 指标组，用声明式算子表达 Trace 概览图使用的 Span 内置指标。
- 让 `TraceChatsResource` 从手工拼接查询参数改为引用内置指标算子。
- 保持改造前后构造出的 charts 配置等价。
- 支持可选 `service_name`，用于服务视角复用同一套 Span 指标定义。

## 0x03 需求范围

- `BaseMetricGroup.query_config` 支持 `raw` 参数：默认返回告警/策略侧格式，`raw=True` 返回 UnifyQuery 原始查询配置。
- 定义 `SpanMetricGroup`：通过 `kind` 区分主调、被调，通过 `service_name` 增加服务过滤。
- 第一版 Span 算子覆盖 Trace 概览图现有指标：请求数、错误数、错误率、平均耗时、P50、P95 和 P99。
- `TraceChatsResource` 提供 `build_target`，集中补齐前端图表 target 需要但 `CompilerMixin.config` 不提供的字段。
- 补充单元测试或快照测试，证明算子配置和 charts 配置保持等价。

## 0x04 非目标

- 本期不实现 `SpanMetricGroup.handle`。
- 本期不把成功数、成功率、异常数和异常率扩展为完整 RED 指标集合。
- 本期不调整 Trace 图表的展示布局、图表数量和前端协议。
- 本期不改造 `ResourceMetricGroup` 与 `TrpcMetricGroup` 的查询语义。

## 0x05 方法论

- 先冻结 `TraceChatsResource` 现有 charts 输出作为等价基线。
- 再把查询语义迁移到 `SpanMetricGroup`，把图表兼容字段保留在 `build_target`。
- 最后通过 raw query config 与 charts 快照验证，确认改造只改变构造方式，不改变对外配置。

## 0x06 验收标准

- `SpanMetricGroup.query_config(raw=True)` 能生成 Trace 概览图所需的 `7` 类 Span 指标查询配置。
- `TraceChatsResource.perform_request` 在不传 `service_name` 时，返回 charts 配置与改造前一致。
- 传入 `service_name` 时，每个 query config 都追加服务过滤，target data 也携带 `service_name`。
- `ResourceMetricGroup` 与 `TrpcMetricGroup` 默认 `query_config` 行为不变。
- 相关测试或可执行验证通过，并记录到同目录 `PLAN.md`。

## 0x07 参考

- 实施方案：[PLAN.md](./PLAN.md)
- `<源码>` bk-monitor/bkmonitor/packages/apm_web/trace/resources.py
- `<源码>` bk-monitor/bkmonitor/packages/apm_web/handlers/metric_group/groups/resource.py
- `<源码>` bk-monitor/bkmonitor/packages/apm_web/handlers/metric_group/groups/trpc.py
- `<源码>` bk-monitor/bkmonitor/bkmonitor/data_source/unify_query/builder.py
