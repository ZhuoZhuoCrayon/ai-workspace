---
title: 告警日志查询支持 Doris 数据源
tags: [log, unify-query, doris, data-source]
description: 日志告警查询切换 UnifyQuery 后，将 _index 替换为 ES/Doris 兼容的 time 字段
created: 2026-03-12
updated: 2026-03-12
---

# 告警日志查询支持 Doris 数据源

## 0x01 背景

### a. Why

Doris 不支持使用 `_index` 字段。当日志数据源切换到 UnifyQuery 后，UnifyQuery 会将请求路由到不同的存储后端（ES / Doris），需要使用两者都兼容的字段。

### b. 目标

在 `LogSearchTimeSeriesDataSource` 生成 UnifyQuery 查询配置时，将 `_index` 替换为 `time`，确保 ES 和 Doris 后端均能正常处理。

## 0x02 实现路线

### a. 建议的方案

重写 `LogSearchTimeSeriesDataSource.to_unify_query_config`，当 `field_name == "_index"` 时替换为 `time`。

### b. 约束

- 仅影响 UnifyQuery 查询路径，不影响直连 ES 的老链路
- 仅影响走 `to_unify_query_config` 的 UnifyQuery 聚合查询路径；UnifyQuery 原始日志查询会清空 `field_name`，不受此改动影响
- `LogSearchLogDataSource` 继承自 `LogSearchTimeSeriesDataSource`，会自动继承此改动
- `_index` 是 ES 内置元字段，语义为"文档所在索引"；替换为 `time` 后语义变为按时间字段做 COUNT 聚合，需确认 UnifyQuery 后端对 `count(time)` 的处理等价于 `count(_index)`

## 0x03 参考

- 关联需求：`knowledge/bkmonitor/issues/2026-02-10-log-ds-to-unify-query/README.md`
