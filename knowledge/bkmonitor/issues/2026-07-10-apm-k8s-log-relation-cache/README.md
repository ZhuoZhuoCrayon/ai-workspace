---
title: APM 关联容器日志采集项慢接口优化
tags: [apm, log-relation, k8s, cache, latency, index-set]
description: 通过后台任务预缓存服务与 K8S 容器日志索引的关联关系，消除 APM 日志页面首次打开时的逐服务关系查询瓶颈
created: 2026-07-10
updated: 2026-07-17
---

# APM 关联容器日志采集项慢接口优化

## 0x01 背景

### a. 问题

APM 日志页面首次打开时，`LogRelationListResource` 和 `LogInfoResource` 响应极慢，耗时达分钟级。

根因在 `process_metric_relations` 分支：当前为每个服务独立调用 `ServiceLogHandler.list_indexes_by_relation`，通过 `RelationQ.query` 向 UnifyQuery（UQ）发起 `relation/multi_resource_range` 请求。一个 APM 应用通常有 `100+` 服务，产生 `100+` 次 UQ 查询。瓶颈在于调用次数而非单次耗时——单次 `query_list` 规模 = workload 数 × handler 类型数 × 关系链路目标数，UQ 侧单次处理耗时 `30s+` 属于正常范围。

前序优化（[PR #10530](https://github.com/TencentBlueKing/bk-monitor/pull/10530)）通过 workload 前置短路减少了无 workload 服务的无效查询，但有 workload 的服务仍然逐服务实时查询 UQ。

### b. 目标

- APM 日志页面的 `LogRelationListResource` 和 `LogInfoResource` 首次打开耗时降至秒级。
- 关系查询结果由后台定时任务预缓存，请求时直接读缓存，不再实时查 UQ。

## 0x02 实现路线

### a. 建议的方案

**缓存前置**：将逐服务实时查 UQ 的关系查询改为后台定时任务批量预计算，结果写入 Redis 缓存，请求时直查缓存。

核心改造路径：

- 新增 `ServiceLogTaskHandler`，批量获取应用下所有服务的 K8S 容器日志索引关联。
- 新增后台任务 `cache_application_k8s_related_indexes`，周期性刷新缓存。
- `ServiceLogHandler.list_indexes_by_relation` 消费侧改为从缓存读取。

### b. 约束

- 缓存策略为追加式更新：只新增或刷新索引条目，不主动删除旧条目，避免后台任务异常时清空缓存导致前端数据丢失。
- 不改变手动关联关系（`process_relation`）、应用数据源关联（`process_datasource`）和 Span 主机关联（`process_span_host`）的行为。
- 前序 issue 的 workload 前置短路逻辑保持不变。

## 0x03 参考

- 前序优化：[PR #10530 · 优化告警中心关联事件查询耗时](https://github.com/TencentBlueKing/bk-monitor/pull/10530)
- [源码 bk-monitor/packages/apm_web/handlers/log_handler.py](https://github.com/TencentBlueKing/bk-monitor/blob/master/bkmonitor/packages/apm_web/handlers/log_handler.py)
- [源码 bk-monitor/packages/apm_web/log/resources.py](https://github.com/TencentBlueKing/bk-monitor/blob/master/bkmonitor/packages/apm_web/log/resources.py)
- [源码 bk-monitor/packages/apm_web/tasks.py](https://github.com/TencentBlueKing/bk-monitor/blob/master/bkmonitor/packages/apm_web/tasks.py)
