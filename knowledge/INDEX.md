# 知识库索引

> 最后更新：2026-07-26

## 0x01 项目知识

| 项目 | 路径 | 数量 | 说明 |
|------|------|------|------|
| ai-workspace | [ai-workspace/](./ai-workspace/INDEX.md) | 4 篇 | AI 工作区 — 知识管理与多项目协作中枢 |
| bkmonitor | [bkmonitor/](./bkmonitor/INDEX.md) | 43 篇 | 蓝鲸监控平台 (bk-monitor/bkmonitor) |
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

- 2026-07-26：更新 [RUM 数据协议](./bkmonitor/articles/2026-07-12-rum-span-data-protocol/README.md)（补充 `attributes.action.type` 的跨端常见值，以及 `attributes.action.frustration.type` 的取值与判定规则）
- 2026-07-25：更新 [RUM 数据协议](./bkmonitor/articles/2026-07-12-rum-span-data-protocol/README.md)（删除 `@blueking/open-telemetry` 0.0.26 源码已移除的旧 Span 字段）
- 2026-07-23：更新 [APM 支持跨应用共享数据源](./bkmonitor/issues/2026-03-03-apm-shared-datasource/README.md)（补充基于访问记录与数据状态缓存筛选候选应用、后台迁移及 SaaS 元数据同步的三阶段运维流程）
- 2026-07-21：更新 [日志 UnifyQuery 环境变量黑名单与 query_string 增强](./bkmonitor/issues/2026-03-05-log-uq-env-whitelist-and-query-string/README.md)（[TencentBlueKing/bk-monitor #11599](https://github.com/TencentBlueKing/bk-monitor/pull/11599) 已合入，进入 Helm 黑名单配置阶段）
- 2026-07-19：更新 [APM Trace 写入 ES 字段类型冲突](./bkmonitor/troubleshooting/apm-trace-es-field-mapping-conflict.md)（补充应用级与 `APM_GLOBAL` 两种 `as_string` 配置方式及索引轮转步骤）
