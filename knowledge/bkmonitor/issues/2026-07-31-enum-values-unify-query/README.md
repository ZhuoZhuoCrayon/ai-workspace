---
title: 枚举值查询接入 UnifyQuery
tags: [unify-query, enum-values, dimension-query, log, trace, event]
description: 让枚举值查询统一进入 UnifyQuery.query_dimensions，并复用数据查询的灰度路由
created: 2026-07-31
updated: 2026-07-31
---

# 枚举值查询接入 UnifyQuery

## 0x01 背景

### a. 问题

日志、调用链和事件的数据查询已经由 UnifyQuery（简称 UQ）判断查询路径。枚举值查询仍存在旁路：
`GetVariableValue.query_dimension()` 直接调用 `DataSource.query_dimensions()`，不会执行
`UnifyQuery.use_unify_query()`。

### b. 目标

- 所有 DataSource 枚举值查询先构造 UQ，再调用 `UnifyQuery.query_dimensions()`。
- 单数据源先判断 UQ 枚举能力，再复用 `use_unify_query()` 选择 UQ `tag_values` 或原 DataSource。
- 外部接口和各 DataSource 的返回结构保持不变。

## 0x02 实现路线

### a. 方案

枚举值查询在 `UnifyQuery.query_dimensions()` 收口：

```text
supports_unify_query_dimensions and use_unify_query()
  -> api.unify_query.tag_values(**params)

otherwise
  -> DataSource.query_dimensions()
```

`GetVariableValue.query_dimension()` 只负责构造单数据源 UQ。`dimension_query` 和
`dimension_count` 继续使用同一个 `query_dimensions()` 入口。

详细设计见 [PLAN.md](./PLAN.md)。

### b. 约束

- 多数据源保留现有 `query_data()` 表达式查询。
- BKData、InfluxDB 等非目标 DataSource 保留原枚举值查询。
- CMDB、K8S、采集配置和服务实例等非 DataSource 枚举逻辑保持不变。
- 日志、调用链和事件仍只查询首字段。
- 继续使用现有灰度与黑名单，不增加枚举值专用开关。

## 0x03 参考

- [实施方案](./PLAN.md)
- [日志数据源切换 unify-query](../2026-02-10-log-ds-to-unify-query/README.md)
- [日志 UnifyQuery 环境变量黑名单与 query_string 增强](../2026-03-05-log-uq-env-whitelist-and-query-string/README.md)
