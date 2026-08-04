# 知识库索引

> 最后更新：2026-07-31

## 0x01 项目知识

| 项目 | 路径 | 数量 | 说明 |
|------|------|------|------|
| ai-workspace | [ai-workspace/](./ai-workspace/INDEX.md) | 4 篇 | AI 工作区 — 知识管理与多项目协作中枢 |
| bk-cli | [bk-cli/](./bk-cli/INDEX.md) | 0 篇 | 蓝鲸平台 API 命令行工具 |
| bkmonitor | [bkmonitor/](./bkmonitor/INDEX.md) | 45 篇 | 蓝鲸监控平台（bk-monitor/bkmonitor） |
| bkm-skills | [bkm-skills/](./bkm-skills/INDEX.md) | 6 篇 | BlueKing Monitor Skills |
| bk-product-designs | [bk-product-designs/](./bk-product-designs/INDEX.md) | 0 篇 | 蓝鲸监控产品设计协作仓库 |
| bkmonitor_mcp | [bkmonitor_mcp/](./bkmonitor_mcp/INDEX.md) | 1 篇 | 蓝鲸监控 MCP Server |
| bkmonitor-datalink | [bkmonitor-datalink/](./bkmonitor-datalink/INDEX.md) | 3 篇 | 蓝鲸监控数据链路 |
| bkmonitor-ecosystem | [bkmonitor-ecosystem/](./bkmonitor-ecosystem/INDEX.md) | 0 篇 | 蓝鲸监控生态 SDK 与接入 demo（外部版） |
| browser-sdk | [browser-sdk/](./browser-sdk/INDEX.md) | 0 篇 | Datadog Browser SDK |
| crypto-python-sdk | [crypto-python-sdk/](./crypto-python-sdk/INDEX.md) | 0 篇 | BlueKing 轻量级密码学工具包，统一加解密抽象层 |
| throttled-py | [throttled-py/](./throttled-py/INDEX.md) | 8 篇 | High-performance Python rate limiting library |
| 通用知识 | [_shared/](./_shared/INDEX.md) | 1 篇 | 跨项目通用知识 |

## 0x02 最近更新

- 2026-07-31：新增 [APM 跨应用 Trace 检索](./bkmonitor/issues/2026-07-31-apm-cross-app-trace-search/README.md)（通过 Trace 数据源域索引集和 Celery 同步，让 Trace Detail 返回同域跨应用 Span）
- 2026-07-31：新增 [日志、调用链与事件枚举值查询接入 UnifyQuery](./bkmonitor/issues/2026-07-31-enum-values-unify-query/README.md)（枚举值统一进入 `UnifyQuery.query_dimensions()`，复用数据查询的灰度路由）
- 2026-07-28：更新 [RUM 数据协议](./bkmonitor/articles/2026-07-12-rum-span-data-protocol/README.md)（补齐字段状态、修复协议表格边界，并将 `network.connection.type` 对齐浏览器原始枚举）
- 2026-07-27：更新 [优化告警详情主机日志关联准确性](./bkmonitor/issues/2026-04-15-alert-detail-host-collector-log-relation/README.md)（[TencentBlueKing/bk-monitor #11653](https://github.com/TencentBlueKing/bk-monitor/pull/11653) review 通过，进入待合入阶段）
- 2026-07-27：更新 [RUM 数据协议](./bkmonitor/articles/2026-07-12-rum-span-data-protocol/README.md)（补充枚举语义，将 `attributes.document.referrer` 迁移到 View 并废弃 `attributes.outcome.reason`）
