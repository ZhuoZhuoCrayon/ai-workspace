---
title: 日志数据源切换前后保持原始日志结构一致
tags: [log, unify-query, data-source, object-field]
description: 让日志 UnifyQuery 返回的打平对象字段恢复为 ES 查询时期的原始结构
created: 2026-06-08
updated: 2026-06-08
---

# 日志数据源切换前后保持原始日志结构一致

## 0x01 背景

### a. Why

日志数据源从 ES 切换到 UnifyQuery 后，对象（object）字段返回形态发生变化。

差异示例：ES 返回 `{"attributes": {"a": "xxx"}}`，UnifyQuery 返回 `{"attributes.a": "xxx"}`。

如果监控侧不在日志后处理入口收敛结构差异，下游会感知数据源切换带来的协议变化。

### b. 目标

- 切换 UnifyQuery 前后，原始日志中的对象（object）字段结构保持一致。
- 参考现有同类 `process_unify_query_log` 的处理风格，但保持日志时序入口独立实现。
- 保持 `events` 等嵌套（nested）字段原返回格式，不扩大处理范围。

## 0x02 实现路线

### a. 建议的方案

- 在 `LogSearchTimeSeriesDataSource.process_unify_query_log` 中还原对象字段：将 `attributes.a` 收敛为 `attributes: {"a": "xxx"}`。
- 参考日志平台 `merge_nested_data` 的处理方式，对包含 `.` 的字段按路径合并，不预设固定对象根字段。
- 保留现有 `_meta` 清理逻辑，嵌套字段不参与对象还原。

### b. 约束

- 本期只处理对象字段结构兼容，不改查询条件、字段映射和 UnifyQuery 返回协议。
- 各 `process_unify_query_log` 存在细微差异，本期不抽公共辅助函数。
- 日志对象字段不固定，本期不声明 `OBJECT_FIELDS` 固定集合。
- 日志平台逻辑更完整。
- 监控侧只保证结构转换核心逻辑一致。

## 0x03 参考

- 需求背景：[日志数据源切换 unify-query](../2026-02-10-log-ds-to-unify-query/README.md)
- 改动位置：`bkmonitor.data_source.data_source.LogSearchTimeSeriesDataSource.process_unify_query_log`
- 日志平台参考：[`bklog/apps/log_unifyquery/handler/base.py#L646`](https://github.com/TencentBlueKing/bk-monitor/blob/b4783f67d99f8db8bdf37743ef168a05508c3e56/bklog/apps/log_unifyquery/handler/base.py#L646)
