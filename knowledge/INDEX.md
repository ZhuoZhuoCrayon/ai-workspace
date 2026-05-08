# 知识库索引

> 最后更新：2026-05-08

## 0x01 项目知识

| 项目 | 路径 | 数量 | 说明 |
|------|------|------|------|
| ai-workspace | [ai-workspace/](./ai-workspace/INDEX.md) | 4 篇 | AI 工作区 — 知识管理与多项目协作中枢 |
| bkmonitor | [bkmonitor/](./bkmonitor/INDEX.md) | 35 篇 | 蓝鲸监控平台 (bk-monitor/bkmonitor) |
| bkm-skills | [bkm-skills/](./bkm-skills/INDEX.md) | 6 篇 | BlueKing Monitor Skills |
| bkmonitor_mcp | [bkmonitor_mcp/](./bkmonitor_mcp/INDEX.md) | 1 篇 | 蓝鲸监控 MCP Server |
| bkmonitor-datalink | [bkmonitor-datalink/](./bkmonitor-datalink/INDEX.md) | 1 篇 | 蓝鲸监控数据链路 |
| throttled-py | [throttled-py/](./throttled-py/INDEX.md) | 7 篇 | High-performance Python rate limiting library |
| 通用知识 | [_shared/](./_shared/INDEX.md) | 1 篇 | 跨项目通用知识 |

## 0x02 最近更新

- 2026-05-08：更新
  [优化 APM 日志关联列表关系查询长耗时](./bkmonitor/issues/2026-05-06-apm-log-relation-list-uq-latency/README.md)
  至 bkmonitor
  （将 PLAN 从调研态收敛为方案态，并确认无 workload 服务可直接短路关系查询分支）
- 2026-05-07：新增
  [APM Span 内置指标支持声明式引用](./bkmonitor/issues/2026-05-07-apm-span-builtin-metric-declarative-reference/README.md)
  至 bkmonitor
  （将 Trace 概览图 Span 指标查询从手工参数拼接收敛为声明式指标算子）
- 2026-05-06：新增
  [Store 类型抽象边界优化](./throttled-py/issues/2026-05-06-store-typing-abstraction-refactor/README.md)
  至 throttled-py
  （基于 HTTPX transport 设计调研，记录 BaseStore 公共边界与 backend 配对边界的拆分方案）
- 2026-05-06：更新
  [优化首页 TraceID 全局搜索的预计算延迟](./bkmonitor/issues/2026-05-02-overview-trace-id-low-latency-search/README.md)
  至 bkmonitor
  （将 PR #10492 的 review 修复、分层打分不变量与版本锚点回写到 PLAN）
- 2026-05-06：新增
  [优化 APM 日志关联列表关系查询长耗时](./bkmonitor/issues/2026-05-06-apm-log-relation-list-uq-latency/README.md)
  至 bkmonitor
  （记录 `log_relation_list` 样本 Trace 中 `query_multi_resource_range` 35s 级主瓶颈）
