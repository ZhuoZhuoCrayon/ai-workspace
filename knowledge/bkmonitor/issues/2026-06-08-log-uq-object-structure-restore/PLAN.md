---
title: 日志数据源切换前后保持原始日志结构一致 —— 实施方案
tags: [log, unify-query, data-source, object-field]
issue: ./README.md
description: 日志 UnifyQuery 对象字段结构还原的轻量实施方案
created: 2026-06-08
updated: 2026-06-08
---

# 日志数据源切换前后保持原始日志结构一致 —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 调研与约束

- `UnifyQuery.process_unify_query_log` 先把 UnifyQuery（UQ）返回列表中的元字段移入 `_meta`，再由首个数据源执行各自的 `process_unify_query_log`。
- `LogSearchTimeSeriesDataSource.process_unify_query_log` 当前只移除 `_meta`，未还原 `attributes.a` 这类对象（object）字段。
- 日志平台 `_deal_query_result` 会对每条日志执行 `merge_nested_data(log)`。
- `merge_nested_data` 对每个 key 执行 `key.split(".")`，不依赖固定对象字段集合。
- 同文件中 `BkMonitorLogDataSource` / `BkApmTraceDataSource` 已有对象字段还原逻辑，但各入口字段映射、嵌套字段和补齐规则存在差异。

## 0x02 架构设计

结构判断：日志原始记录协议应在数据源后处理层收敛，UQ 的扁平字段形态不能泄漏给下游。

```mermaid
flowchart LR
    A["UnifyQuery raw list"] --> B["UnifyQuery.process_unify_query_log"]
    B --> C["LogSearchTimeSeriesDataSource.process_unify_query_log"]
    C --> D["ES-compatible raw log record"]
```

字段协议：

| 类型 | UnifyQuery 输入 | 监控输出 | 处理 |
| --- | --- | --- | --- |
| 点号字段 | `attributes.a` | `attributes: {"a": "xxx"}` | 按 `.` 路径合并 |
| 多级点号字段 | `attributes.a.b` | `attributes: {"a": {"b": "xxx"}}` | 递归合并 |
| meta | `_meta` | 不返回 | 保持移除 |
| nested | `events` | `events` | 不处理 |
| 普通字段 | `message` | `message` | 原样返回 |

## 0x03 开发方案

落实路径：在日志时序数据源后处理入口完成对象字段还原。

| 变更点 | 目标 |
| --- | --- |
| **Change** `LogSearchTimeSeriesDataSource.process_unify_query_log` | 保留 `_meta` 移除，并在当前方法内按日志平台风格合并点号字段 |
| **Keep** 嵌套字段处理 | `events` 等字段保持 UQ 返回格式，不进入对象还原 |

建议直接使用字段名是否包含 `.` 作为处理条件：

- 字段名包含 `.`：按路径写入结果字典。
- 字段名不包含 `.`：原样写回。
- 日志对象字段不固定，因此不声明 `OBJECT_FIELDS`。

## 0x04 验收与验证

- 补充 `bkmonitor/data_source/tests/test_data_source.py` 中日志数据源用例，断言 `attributes.a` 被还原为 `attributes["a"]`。
- 补充多级点号字段样例，断言 `attributes.a.b` 被还原为 `attributes["a"]["b"]`。
- 断言 `_meta` 不出现在返回记录中。
- 断言 `events` 字段保持原值，不被拆分或二次合并。

## 0x05 实施进展（表格）

| 时间 | 结论性进展 |
| --- | --- |
| `2026-06-08 00:00` | [a] 完成需求与轻量方案沉淀。<br />[b] 明确改动收敛在 `LogSearchTimeSeriesDataSource.process_unify_query_log`，只处理对象字段结构兼容。<br />[c] 确认本期不抽公共辅助函数，各 `process_unify_query_log` 保持独立实现、风格对齐。<br />[d] 确认日志平台按 `key.split(".")` 通用合并点号字段，监控侧不声明 `OBJECT_FIELDS`。 |

## 0x06 参考

- [日志数据源切换 unify-query](../2026-02-10-log-ds-to-unify-query/README.md)
- [日志平台 UnifyQuery 结果处理参考](https://github.com/TencentBlueKing/bk-monitor/blob/b4783f67d99f8db8bdf37743ef168a05508c3e56/bklog/apps/log_unifyquery/handler/base.py#L646)

## 0x07 版本锚点

| 状态 | 分支 | 里程碑 | PR |
| --- | --- | --- | --- |
| 🔄 | `-` | 方案输出 | - |
