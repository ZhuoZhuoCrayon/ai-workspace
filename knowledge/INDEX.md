# 知识库索引

> 最后更新：2026-05-14

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

- 2026-05-14：新增
  [APM 预计算适配共享数据源](./bkmonitor/issues/2026-05-14-apm-precalc-shared-multi-app/README.md)
  至 bkmonitor
  （从 `2026-03-03-apm-shared-datasource/PLAN.md` 的 `0x02.i` 拆出独立 issue，方案改为「单任务多应用窗口」）
- 2026-05-14：更新
  [APM 支持跨应用共享数据源](./bkmonitor/issues/2026-03-03-apm-shared-datasource/README.md)
  至 bkmonitor
  （复查 PR #10583 检索隔离收口，确认旧 review 线程已修复并完成 resolve）
- 2026-05-13：更新
  [Store 类型抽象边界优化](./throttled-py/issues/2026-05-06-store-typing-abstraction-refactor/README.md)
  至 throttled-py
  （将 `BaseStoreMixin` 收敛为 `StoreSpec` / `StoreValidationLogic`，并让 sync / async `BaseStore` 各自持有 backend 槽位）
- 2026-05-10：更新
  [Store 类型抽象边界优化](./throttled-py/issues/2026-05-06-store-typing-abstraction-refactor/README.md)
  至 throttled-py
  （将 PLAN 从 `BaseStore` 局部止血重写为自底向上的 sync / async 分界与复用方案）
- 2026-05-08：更新
  [优化 APM 日志关联列表关系查询长耗时](./bkmonitor/issues/2026-05-06-apm-log-relation-list-uq-latency/README.md)
  至 bkmonitor
  （将 PLAN 从调研态收敛为方案态，并确认无 workload 服务可直接短路关系查询分支）
- 2026-05-07：新增
  [APM Span 内置指标支持声明式引用](./bkmonitor/issues/2026-05-07-apm-span-builtin-metric-declarative-reference/README.md)
  至 bkmonitor
  （将 Trace 概览图 Span 指标查询从手工参数拼接收敛为声明式指标算子）
