# 知识库索引

> 最后更新：2026-06-04

## 0x01 项目知识

| 项目 | 路径 | 数量 | 说明 |
|------|------|------|------|
| ai-workspace | [ai-workspace/](./ai-workspace/INDEX.md) | 4 篇 | AI 工作区 — 知识管理与多项目协作中枢 |
| bkmonitor | [bkmonitor/](./bkmonitor/INDEX.md) | 41 篇 | 蓝鲸监控平台 (bk-monitor/bkmonitor) |
| bkm-skills | [bkm-skills/](./bkm-skills/INDEX.md) | 6 篇 | BlueKing Monitor Skills |
| bkmonitor_mcp | [bkmonitor_mcp/](./bkmonitor_mcp/INDEX.md) | 1 篇 | 蓝鲸监控 MCP Server |
| bkmonitor-datalink | [bkmonitor-datalink/](./bkmonitor-datalink/INDEX.md) | 1 篇 | 蓝鲸监控数据链路 |
| bkmonitor-ecosystem | [bkmonitor-ecosystem/](./bkmonitor-ecosystem/INDEX.md) | 0 篇 | 蓝鲸监控生态 SDK 与接入 demo（外部版） |
| throttled-py | [throttled-py/](./throttled-py/INDEX.md) | 7 篇 | High-performance Python rate limiting library |
| 通用知识 | [_shared/](./_shared/INDEX.md) | 1 篇 | 跨项目通用知识 |

## 0x02 最近更新

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
- 2026-06-03：新增
  [RUM 领域信息收集：核心术语、机制与规范索引](./bkmonitor/articles/2026-06-03-rum-observability-domain-primer/README.md)
  至 bkmonitor
  （按规范聚合整理 RUM 领域常见术语、机制解释和参考链接，作为领域建设入门资料）
- 2026-06-02：更新
  [错误视图 tRPC 场景适配](./bkmonitor/issues/2026-05-31-apm-error-view-trpc-adaptation/README.md)
  至 bkmonitor
  （补齐里程碑 3：错误详情通过返回码备注规则展示 `返回码 - xxxx（备注）`）
