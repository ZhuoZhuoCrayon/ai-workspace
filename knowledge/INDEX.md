# 知识库索引

> 最后更新：2026-06-08

## 0x01 项目知识

| 项目 | 路径 | 数量 | 说明 |
|------|------|------|------|
| ai-workspace | [ai-workspace/](./ai-workspace/INDEX.md) | 4 篇 | AI 工作区 — 知识管理与多项目协作中枢 |
| bkmonitor | [bkmonitor/](./bkmonitor/INDEX.md) | 42 篇 | 蓝鲸监控平台 (bk-monitor/bkmonitor) |
| bkm-skills | [bkm-skills/](./bkm-skills/INDEX.md) | 6 篇 | BlueKing Monitor Skills |
| bkmonitor_mcp | [bkmonitor_mcp/](./bkmonitor_mcp/INDEX.md) | 1 篇 | 蓝鲸监控 MCP Server |
| bkmonitor-datalink | [bkmonitor-datalink/](./bkmonitor-datalink/INDEX.md) | 1 篇 | 蓝鲸监控数据链路 |
| bkmonitor-ecosystem | [bkmonitor-ecosystem/](./bkmonitor-ecosystem/INDEX.md) | 0 篇 | 蓝鲸监控生态 SDK 与接入 demo（外部版） |
| throttled-py | [throttled-py/](./throttled-py/INDEX.md) | 7 篇 | High-performance Python rate limiting library |
| 通用知识 | [_shared/](./_shared/INDEX.md) | 1 篇 | 跨项目通用知识 |

## 0x02 最近更新

- 2026-06-08：更新
  [错误视图 tRPC 场景适配](./bkmonitor/issues/2026-05-31-apm-error-view-trpc-adaptation/README.md)
  至 bkmonitor
  （补充里程碑 3：错误列表返回码使用 `exception_alias` 展示基础别名，原错误详情返回码备注顺延为里程碑 4）
- 2026-06-08：新增
  [日志数据源切换前后保持原始日志结构一致](./bkmonitor/issues/2026-06-08-log-uq-object-structure-restore/README.md)
  至 bkmonitor
  （将日志 UnifyQuery 打平对象字段还原为 ES 查询时期的原始结构，保持数据源切换前后协议一致）
- 2026-06-08：更新
  [APM Span 详情支持 Links 反向关联展示](./bkmonitor/issues/2026-06-04-apm-span-links-reverse-relation/README.md)
  至 bkmonitor
  （确认 Links 查询不传时间范围，由 `query_span_list` 后台按保留期补全，并扩展 `links.trace_id` / `links.span_id` 精确检索）
- 2026-06-04：更新
  [主机场景容器事件关联准确性提升](./bkmonitor/issues/2026-06-03-alert-host-k8s-event-relation-accuracy/README.md)
  至 bkmonitor
  （PR #10922 二轮 Review 通过，节点详情反查性能风险标记为已知问题）
- 2026-06-04：新增
  [APM Span 详情支持 Links 反向关联展示](./bkmonitor/issues/2026-06-04-apm-span-links-reverse-relation/README.md)
  至 bkmonitor
  （新增 `ListLinkResource` 方案，通过 TraceID 和 SpanID 过滤并返回标准 Link 列表）
- 2026-06-04：新增
  [【告警中心】优化关联日志条件构造不准确的问题](./bkmonitor/issues/2026-06-04-alert-log-search-condition-accuracy/README.md)
  至 bkmonitor
  （将日志告警关联日志的过滤语义收敛到有效 `keyword`，避免语句模式忽略策略过滤条件）
