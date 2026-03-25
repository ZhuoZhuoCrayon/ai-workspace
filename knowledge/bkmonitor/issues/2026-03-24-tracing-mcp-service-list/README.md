---
title: Tracing MCP 新增服务列表工具
tags: [apm, tracing, mcp, service-list, entity-set]
description: 为 Tracing MCP 新增服务列表查询接口，返回服务的系统、平台和日志关联信息
created: 2026-03-24
updated: 2026-03-24
---

# Tracing MCP 新增服务列表工具

## 0x01 背景

Tracing MCP 需要服务列表查询能力，返回每个服务的 RPC 框架、SDK、指标时序类型、容器平台关联、日志关联等结构化信息。

现有 `apm_web.metric.resources.ServiceListResource` 面向前端表格渲染，字段与 MCP 不匹配，无法复用。

## 0x02 目标

1. 新增 MCP 专用的服务列表接口。
2. 数据统一走 `EntitySet`，按需扩展。
3. 清理关联组件中的冗余设计。

## 0x03 接口契约

### a. 请求

| 字段 | 类型 | 必选 | 说明 |
|------|------|------|------|
| bk_biz_id | int | 是 | 业务 ID |
| app_name | string | 是 | 应用名称 |
| service_names | list[string] | 否 | 不传返回全部服务 |

### b. 响应

列表，每个元素：

| 字段 | 类型 | 说明 |
|------|------|------|
| service_name | string | 服务名 |
| service_language | string | 服务语言 |
| system | object | 系统信息；无则为 `{}` |
| system.name | string | 框架（trpc、tars、grpc ⋯⋯） |
| system.sdk | string | SDK（galileo、opentelemetry ⋯⋯） |
| system.temporality | string | 时序类型（delta、cumulative） |
| platform | object | 容器平台信息 |
| platform.name | string | 平台名（k8s） |
| platform.relations | list | Workload 列表 |
| log_relations | list | 日志关联 |
| log_relations[].is_app_datasource | bool | 是否为应用数据源 |
| log_relations[].bk_biz_id | int | 关联业务 ID |
| log_relations[].index_set_id | int | 索引集 ID |

## 0x04 附带优化

1. `_service_log_indexes_map` 补充 `bk_biz_id`。
2. `get_first_log_index_set_id_or_none` 优先匹配应用数据源和同业务。
3. `get_rpc_service_config_or_none` 通用化为 `get_system`。
4. `MetricTemporality.get_metric_config` 拆解为类常量。
5. 移除 `apm_web.meta.resources.ServiceConfigResource`。

## 0x05 约束

- `apm_web.service.resources.ServiceConfigResource`（服务配置 CRUD）保留。
- `get_system` 改造需适配所有现有消费方。
