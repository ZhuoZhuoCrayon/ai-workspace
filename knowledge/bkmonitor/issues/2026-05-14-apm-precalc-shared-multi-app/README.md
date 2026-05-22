---
title: APM 预计算适配共享数据源
tags: [apm, pre-calculate, shared-datasource, multi-app, bmw]
description: 让单 BMW 预计算任务感知共享 data_id 下的多个应用，不破坏现有任务模型与持久化键
created: 2026-05-14
updated: 2026-05-22
---

# APM 预计算适配共享数据源

## 0x01 背景

### a. Why

共享数据源把一个 `data_id` 与多个 APM 应用关联。BMW 预计算任务在 `data_id` 维度静态绑定单应用上下文：

- `Processor.baseInfo`：`MetadataCenter.GetBaseInfo(dataId)`，构造期注入。
- `MetricProcessor.appName`：`baseInfo.AppName`，构造期注入。
- `MetricDimensionsHandler.promClient` 的 token：`MetadataCenter.GetToken(dataId)`，构造期注入。

直接复用现状会导致：

- 多应用的应用元数据在 Consul 互相覆盖。
- 所有 Span 归属到 Consul 最后写入的应用。
- 上报 Token 绑定首应用，其余应用指标走错租户。
- 历史 Span 回补仅按 `trace_id` 查 ES，跨应用偶发 `trace_id` 撞库读到对方 Span。

### b. 目标

- BMW 任务模型保持：`taskUniId` 仍按 `data_id` 派生，共享 `data_id` 单点绑定一份 Kafka 消费。
- 任务内多应用感知：`Processor` / `MetricProcessor` 按应用实例化，每应用独立持有应用上下文。
- 持久化键不变：子窗口 `sync.Map`、布隆过滤器、预计算结果表 ES `_id` 保留裸 `trace_id`。
- 独占模式行为完全保留。

## 0x02 实现路线

### a. 建议的方案

方案 4「单任务多应用窗口」。

- 在 `KafkaNotifier` 与 `DistributiveWindow` 之间插入 `Dispatcher`，按 Span 顶层 `(bk_biz_id, app_name)` 路由到对应应用的 `appBundle`。
- `appBundle` 是应用维度的三元组 `(DistributiveWindow, Processor, MetricProcessor)`，每应用一份。
- `Proxy` 仍是单实例，仅 `prometheusMetricsHandler` 字段升级为 `map[AppKey]*MetricDimensionsHandler`。

详细方案见 [PLAN.md](./PLAN.md)。

### b. 约束

- 共享池规模上限由 SaaS 侧控制，BMW 侧不再考虑 `M` 的上限。
- `Processor.traceEsQueryLimiter` 每 `Processor` 独立，与共享池大小线性。
- 依赖父 issue 的 Consul 协议扩展：共享模式 Value 包含 `apps[]`，元素见 [PLAN.md `0x02.e`](./PLAN.md#e-consul-协议与变更感知)。
- 依赖父 issue 的数据写入约定：共享场景下，bk-collector 在 Span 顶层注入 `bk_biz_id` 与 `app_name`，来源是应用上报 Token 解析得到的应用上下文。

## 0x03 参考

- 父 issue：[APM 支持跨应用共享数据源](../2026-03-03-apm-shared-datasource/README.md)
- 实施方案：[PLAN.md](./PLAN.md)
- BMW 预计算模块：`pkg/bk-monitor-worker/internal/apm/pre_calculate/**`
- bk-collector 共享场景 Span 顶层字段注入：`pkg/collector/exporter/converter/traces.go`
