---
title: 优化 APM 日志关联列表关系查询长耗时 —— 调研 PLAN
tags: [apm, log-relation, relation-query, unify-query, latency]
issue: knowledge/bkmonitor/issues/2026-05-06-apm-log-relation-list-uq-latency/README.md
description: 记录 APM 日志关联列表接口长耗时样本中的 UnifyQuery 关系查询瓶颈，暂不展开优化方案
created: 2026-05-06
updated: 2026-05-06
---

# 优化 APM 日志关联列表关系查询长耗时 —— 调研 PLAN

> 基于 [README.md](./README.md) 制定。

## 0x01 调研与约束

### a. 样本信息

- 环境：bkop。
- 观测应用：`bkmonitor_production`。
- Trace ID：`9a9aaba7214aa92cd4edd6bfba7102b2`。
- 入口：`POST /apm/service_log/log/log_relation_list/`。
- 目标接口：APM 日志关联列表。
- 时间窗口：`7d`。
- 当前阶段只记录瓶颈，不编写优化方案。

### b. 关键约束

- 现有结论来自单个慢 Trace，只能作为瓶颈样本，不能直接代表全量分布。
- 当前 Trace 展示的是 Web 侧客户端等待耗时，UnifyQuery 服务端内部耗时仍需补证据。
- span 未记录 `query_multi_resource_range` 请求体，下一阶段需要补充请求规模、路径数量和返回规模。

## 0x02 瓶颈拓扑

当前样本的主瓶颈在关系查询分支：Web 侧等待 UnifyQuery `relation/multi_resource_range` 返回。

- 客户端等待耗时为 `35.535s`。
- 该耗时占入口总耗时约 `98.5%`。

```text
[入口] POST /apm/service_log/log/log_relation_list/ ← 36.090s / frustrated
  └─[资源] LogRelationListResource.perform_request ← 36.029s
      ├─[预处理] get_biz_index_sets_with_cache / search_index_set ← 0.469s / 非主瓶颈
      └─[内部] log_relation_list / ThreadPoolExecutor 四分支
          ├─[分支] process_relation ← 手动关联匹配，当前样本未见长耗时
          ├─[分支] process_datasource → detail_application ← 0.319s / 非主瓶颈
          ├─[主瓶颈] process_metric_relations
          │   └─ ServiceLogHandler.list_indexes_by_relation
          │       └─ RelationQ.query / query_multi_resource_range ← 35.536s
          │           └─ [待证根因] UQ relation 多资源范围查询客户端等待 ← 35.535s
          └─[分支] process_span_host ← 本次请求无 span_id，非主瓶颈
```

非主瓶颈：

- log-search 索引集接口耗时 `0.459s`～`0.469s`，不是当前 `36s` 长尾主因。
- APM 应用详情接口耗时 `0.314s`～`0.319s`，不是当前主因。
- MySQL、Redis 和 IAM span 大多为毫秒级，不解释当前长耗时。

## 0x03 待补证据

- 多样本分布：确认 `log_relation_list` 慢请求是否稳定集中在 `query_multi_resource_range`。
- UnifyQuery 服务端：补充 `relation/multi_resource_range` 服务端 trace、日志或指标。
- 请求规模：记录 `query_list` 数量、`path_resource`、时间窗口、返回节点数和数据源数量。
- 缓存状态：确认 `log_relation_list` 缓存 miss 与 `get_biz_index_sets_with_cache` 命中状态。
- 参数敏感性：对比 `7d`、`1d`、`1h` 等窗口下关系查询耗时变化。

## 0x04 验收与验证

- 本阶段交付物是需求与调研 PLAN，不包含代码实现。
- 后续进入优化方案前，至少补齐多样本分布和 UnifyQuery 服务端证据。
- 优化方案需要能解释 `query_multi_resource_range` 的耗时来源，而不是只绕开当前样本。

## 0x05 实施进展

| 时间 | 对应设计片段 | 结论调整概要 | 改动 / 验证 |
| --- | --- | --- | --- |
| `2026-05-06 11:00` | `0x02` | 确认 UQ relation 调用为主瓶颈。 | 主干只保留可读瓶颈拓扑。 |

## 0x06 参考

- 样本 Trace：`bkmonitor_production / 9a9aaba7214aa92cd4edd6bfba7102b2`
- `<源码> bk-monitor/bkmonitor/packages/apm_web/log/resources.py`
- `<源码> bk-monitor/bkmonitor/packages/apm_web/handlers/log_handler.py`
- `<源码> bk-monitor/bkmonitor/packages/apm_web/topo/handle/relation/query.py`

## 0x07 版本锚点

- 分支：待定
- PR：待定
