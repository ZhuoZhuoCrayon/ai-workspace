---
title: APM 支持跨应用共享数据源
tags: [apm, datasource, es, shared-storage]
description: 支持多 APM 应用复用同一数据源（bk_data_id），压缩 ES 索引数量，降低数据链路资源消耗
created: 2026-03-03
updated: 2026-03-03
---

# APM 支持跨应用共享数据源

## 0x01 背景

### a. Why

一个应用对应一个调用链真实数据源，将在 ES 集群上创建 N 多索引，严重消耗数据链路资源。希望支持多应用复用数据源，压缩 ES 索引数量。

### b. 目标

- 多应用复用同一 `bk_data_id`，压缩 ES 索引数量
- 查询透明兼容，通过 `bk_biz_id` + `app_name` 字段隔离
- 通用方案，预留日志/指标共享空间，本期聚焦 Trace

## 0x02 需求

### a. 新建应用

`CreateApplicationResource` 增加参数 `shared_datasource_types: list`（如 `["trace"]`），声明哪些数据源使用共享模式。也可通过 `space_type` 自动判断。

### b. 共享数据源管理

`apm/models/datasource.py`

- **模型**：维护共享数据源计数器（`BaseSharedDataSource`）：配额（quota）/ 使用量（usage_count）/ 数据类型（data_type）/ 是否启用；元数据信息（bk_data_id / result_table_id / 按 data_type 扩展字段如 index_set_id）。通过继承得到 `SharedTraceDataSource`，后续其他类型同理扩展。
- **创建应用**：选择使用量最低的共享源（不存在则新建） → 计数 +1；限制：共享数据源暂不创建日志索引集
- **删除应用**：计数 -1
- **结果表注册**：`create_or_update_result_table` 时使用业务 0 注册全局，table_id 使用 `apm_global.shared_trace_{seq}` 全局命名

### c. ApmDataSourceConfigBase 变更

- 支持共享模式：通过 `shared_datasource_id` 关联共享池，共享时不再自建结果表/索引
- `start` / `stop`：共享模式下不操作结果表及索引
- `apply_datasource`：共享模式 → 分配共享链路信息并 save；否则 → 走原有 `create_data_id` / `create_or_update_result_table`

### d. 接收端（bk-collector）

清洗时补充 `bk_biz_id`、`app_name` 作为字段（Token 反解获取）。

### e. 查询

- **metadata 路由层**：共享结果表注册在业务 0 下，需支持以 `bk_biz_id` 作为 filter 查询全局结果表（跨团队依赖项，需确认 metadata 当前能力）
- **SpanQuery**：封装通用方法，增加 `bk_biz_id` + `app_name` 过滤
- **TopoHandler.list_trace_ids**：增加过滤条件
- **TraceDataSource.get_q**：增加过滤条件
- **全文检索**：`(DataTypeLabel.LOG, DataSourceLabel.BK_APM)` 非预计算场景加过滤

## 0x03 参考

- `apm/models/datasource.py`：ApmDataSourceConfigBase / TraceDataSource
- `apm/models/application.py`：ApmApplication
- `apm/resources.py`：CreateApplicationResource / DeleteApplicationResource
- `apm/core/handlers/query/span_query.py`：SpanQuery
- `apm/core/discover/base.py`：TopoHandler.list_trace_ids
