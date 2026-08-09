# 知识库索引

> 最后更新：2026-08-09

## 0x01 项目知识

| 项目 | 路径 | 数量 | 说明 |
|------|------|------|------|
| ai-workspace | [ai-workspace/](./ai-workspace/INDEX.md) | 4 篇 | AI 工作区 — 知识管理与多项目协作中枢 |
| bk-cli | [bk-cli/](./bk-cli/INDEX.md) | 0 篇 | 蓝鲸平台 API 命令行工具 |
| bkmonitor | [bkmonitor/](./bkmonitor/INDEX.md) | 46 篇 | 蓝鲸监控平台（bk-monitor/bkmonitor） |
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

- 2026-08-09：更新 [RUM 分层统一查询](./bkmonitor/issues/2026-08-07-rum-unified-query/README.md)（统一 Span 接口命名、里程碑和 `/rum/search/{API}/` 路由）
- 2026-08-08：更新 [0 点活动上线导致 RPC 指标 series 暴涨](./bkmonitor/troubleshooting/rpc-series-spike-on-activity-launch.md)（补充空投节事前预测与实测复盘，验证潜伏组合、未见服务代理和容器维度治理效果）
- 2026-08-06：更新 [APM 跨应用 Trace 检索](./bkmonitor/issues/2026-07-31-apm-cross-app-trace-search/README.md)（[TencentBlueKing/bk-monitor #11794](https://github.com/TencentBlueKing/bk-monitor/pull/11794) review 通过，进入待合入阶段）
- 2026-07-31：新增 [APM 跨应用 Trace 检索](./bkmonitor/issues/2026-07-31-apm-cross-app-trace-search/README.md)（通过 Trace 数据源域索引集和 Celery 同步，让 Trace Detail 返回同域跨应用 Span）
- 2026-07-31：新增 [日志、调用链与事件枚举值查询接入 UnifyQuery](./bkmonitor/issues/2026-07-31-enum-values-unify-query/README.md)（枚举值统一进入 `UnifyQuery.query_dimensions()`，复用数据查询的灰度路由）
