---
title: Tracing MCP 新增服务列表工具 —— 实施方案
tags: [apm, tracing, mcp, service-list, entity-set]
issue: ./README.md
description: 服务列表接口实现与关联组件优化方案
created: 2026-03-24
updated: 2026-03-24
---

# Tracing MCP 新增服务列表工具 —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 新增 ServiceListResource

### a. 位置

- 接口：`apm_web.service.resources.ServiceListResource`
- 路由：`apm_web.service.views`，新增 `ResourceRoute`

### b. 数据组装

所有字段通过 `EntitySet` 获取，不引入额外数据源。

| 字段 | 来源 |
|------|------|
| service_name | `service_names` |
| service_language | `_service_node_map` 中的 `extra_data.language` |
| system | `get_system`（改造后，见 0x02-b） |
| platform | `get_workloads`，固定 `name=k8s` |
| log_relations | `get_log_relations`（新增，暴露 `_service_log_indexes_map`） |

---

## 0x02 优化改造

### a. 日志索引映射与选取

`_service_log_indexes_map`：每条记录追加 `bk_biz_id`——应用数据源取 `self.bk_biz_id`，关联日志取 `relation.related_bk_biz_id`。新增字段不影响现有下游。

`get_first_log_index_set_id_or_none`：选取优先级改为——

1. `is_app_datasource=True`
2. `bk_biz_id == self.bk_biz_id`
3. 兜底取第一条

返回类型不变（`int | None`），调用方无需改动。

### b. system 提取通用化

核心决策：

- `get_rpc_service_config_or_none` 改名 `get_system`，从节点 `system`、`sdk` 字段提取 `{name, sdk, temporality}`，不限于 RPC 服务。
- 无 system 返回 `{}`（不是 `None`），消费方无需空判断。
- RPC 判断从 `ServiceHandler` 收敛到 `Vendor`：新增 `Vendor.is_rpc_system`，集中维护 RPC 系统集合（trpc、tars）。

改造范围：

- `ServiceHandler.get_rpc_service_config_or_none`：改名、调整返回结构。
- `EntitySet.get_rpc_service_config_or_none`：同步改名，委托 `ServiceHandler.get_system`。

消费方适配：

| 消费方 | 适配要点 |
|--------|---------|
| `enricher.RPCSystemDiscoverer` | 改调 `get_system`，用 `Vendor.is_rpc_system` 判断 |
| `enricher.RPCEnricher` | 从返回值读 `temporality`，用 `Vendor.is_rpc_system` 判断 |
| `builtin.apm.discover_caller_callee` | 用 `Vendor.is_rpc_system` 设置 `exists` |

### c. MetricTemporality 常量化

`get_metric_config` 返回的 `server_filter_method`、`server_field`、`service_field` 均为固定值，提升为类常量（`SERVER_FILTER_METHOD`、`SERVER_FIELD`、`SERVICE_FIELD`），删除方法本身。

影响点：

| 调用方 | 说明 |
|--------|------|
| `ServiceHandler`（已改为 `get_system`） | 不再需要 |
| `builtin.apm.discover_caller_callee` | 直接引用类常量 |
| `TrpcMetricGroup.get_server_config` | 直接引用类常量 |

### d. 移除冗余接口

删除 `apm_web.meta.resources.ServiceConfigResource` 及其在 `apm_web.meta.views` 中的路由和 import。

注意与 `apm_web.service.resources.ServiceConfigResource` 同名但职责不同，后者保留。

---

## 0x03 变更清单

| 变更 | 位置 |
|------|------|
| 新增 `ServiceListResource` | `apm_web.service.resources` |
| 注册路由 | `apm_web.service.views` |
| `EntitySet` 扩展 | `apm_web.strategy.dispatch.entity` |
| `ServiceHandler` 改造 | `apm_web.handlers.service_handler` |
| `Vendor` 扩展 | `constants.apm` |
| `MetricTemporality` 常量化 | `constants.apm` |
| enricher 适配 | `apm_web.strategy.dispatch.enricher` |
| builtin/apm 适配 | `monitor_web.scene_view.builtin.apm` |
| trpc metric group 适配 | `apm_web.handlers.metric_group.groups.trpc` |
| 移除 `ServiceConfigResource` | `apm_web.meta.resources`、`apm_web.meta.views` |

---

*制定日期：2026-03-24*
