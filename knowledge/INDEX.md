# 知识库索引

> 最后更新：2026-06-10

## 0x01 项目知识

| 项目 | 路径 | 数量 | 说明 |
|------|------|------|------|
| ai-workspace | [ai-workspace/](./ai-workspace/INDEX.md) | 4 篇 | AI 工作区 — 知识管理与多项目协作中枢 |
| bkmonitor | [bkmonitor/](./bkmonitor/INDEX.md) | 42 篇 | 蓝鲸监控平台 (bk-monitor/bkmonitor) |
| bkm-skills | [bkm-skills/](./bkm-skills/INDEX.md) | 6 篇 | BlueKing Monitor Skills |
| bkmonitor_mcp | [bkmonitor_mcp/](./bkmonitor_mcp/INDEX.md) | 1 篇 | 蓝鲸监控 MCP Server |
| bkmonitor-datalink | [bkmonitor-datalink/](./bkmonitor-datalink/INDEX.md) | 2 篇 | 蓝鲸监控数据链路 |
| bkmonitor-ecosystem | [bkmonitor-ecosystem/](./bkmonitor-ecosystem/INDEX.md) | 0 篇 | 蓝鲸监控生态 SDK 与接入 demo（外部版） |
| throttled-py | [throttled-py/](./throttled-py/INDEX.md) | 7 篇 | High-performance Python rate limiting library |
| 通用知识 | [_shared/](./_shared/INDEX.md) | 1 篇 | 跨项目通用知识 |

## 0x02 最近更新

- 2026-06-10：更新
  [日志 UnifyQuery 环境变量白名单与 query_string 增强](./bkmonitor/issues/2026-03-05-log-uq-env-whitelist-and-query-string/README.md)
  至 bkmonitor
  （补充日志聚类表 `_clustered` 后缀统一走 UnifyQuery 的方案与验证结论）
- 2026-06-10：新增
  [bk-collector 自适应限流](./bkmonitor-datalink/issues/2026-06-10-collector-adaptive-throttling/README.md)
  至 bkmonitor-datalink
  （以 CPU / 内存真实资源水位驱动按 endpoint 分级的有损降级，避免 collector 高负载下被压垮导致用户数据持续中断）
- 2026-06-08：更新
  [日志数据源切换 unify-query](./bkmonitor/issues/2026-02-10-log-ds-to-unify-query/README.md)
  至 bkmonitor
  （补充 Pod 同步环境备注，并整理对账方案文档格式）
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
