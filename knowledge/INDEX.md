# 知识库索引

> 最后更新：2026-10-30

## 0x01 项目知识

| 项目 | 路径 | 数量 | 说明 |
|------|------|------|------|
| ai-workspace | [ai-workspace/](./ai-workspace/INDEX.md) | 6 篇 | AI 工作区 — 知识管理与多项目协作中枢 |
| bk-cli | [bk-cli/](./bk-cli/INDEX.md) | 0 篇 | 蓝鲸平台 API 命令行工具 |
| bkmonitor | [bkmonitor/](./bkmonitor/INDEX.md) | 52 篇 | 蓝鲸监控平台（bk-monitor/bkmonitor） |
| bkm-skills | [bkm-skills/](./bkm-skills/INDEX.md) | 6 篇 | BlueKing Monitor Skills |
| bk-product-designs | [bk-product-designs/](./bk-product-designs/INDEX.md) | 0 篇 | 蓝鲸监控产品设计协作仓库 |
| bkmonitor_mcp | [bkmonitor_mcp/](./bkmonitor_mcp/INDEX.md) | 1 篇 | 蓝鲸监控 MCP Server |
| bkmonitor-datalink | [bkmonitor-datalink/](./bkmonitor-datalink/INDEX.md) | 4 篇 | 蓝鲸监控数据链路 |
| bkmonitor-ecosystem | [bkmonitor-ecosystem/](./bkmonitor-ecosystem/INDEX.md) | 0 篇 | 蓝鲸监控生态 SDK 与接入 demo（外部版） |
| browser-sdk | [browser-sdk/](./browser-sdk/INDEX.md) | 0 篇 | Datadog Browser SDK |
| crypto-python-sdk | [crypto-python-sdk/](./crypto-python-sdk/INDEX.md) | 0 篇 | BlueKing 轻量级密码学工具包，统一加解密抽象层 |
| throttled-py | [throttled-py/](./throttled-py/INDEX.md) | 8 篇 | High-performance Python rate limiting library |
| 通用知识 | [_shared/](./_shared/INDEX.md) | 1 篇 | 跨项目通用知识 |

## 0x02 最近更新

- 2026-10-30：更新 [RUM 分层统一查询](./bkmonitor/issues/2026-08-07-rum-unified-query/README.md)（补充 Session / View 降级检索设计、验证记录与 PR 交付状态）
- 2026-10-26：更新 [APM 服务数据状态下沉到后台服务发现](./bkmonitor/issues/2026-09-16-apm-service-data-status-heartbeat/README.md)（性能分析状态改造与旧查询、缓存清理已合入，本期代码改造完成）
- 2026-10-23：更新 [bk-collector 指标元信息采集与同步](./bkmonitor-datalink/issues/2026-09-15-collector-metric-metadata/README.md)（完成本地生产模块、双 Bloom 轮转、防抖、配额熔断与协议验证，记录发布依赖）
- 2026-10-23：新增 [APM 日志存储支持切换 ES 集群](./bkmonitor/issues/2026-10-23-apm-log-storage-cluster-switch/README.md)（补齐选择入口与保存后刷新，已提单并加入排期）
- 2026-10-23：更新 [通用聊天 Agent 桥接组件](./ai-workspace/issues/2026-10-17-agent-chat-bridge/README.md)（执行器与模型全局切换修复已直接推送 `main`，上下文仍按会话保留）
