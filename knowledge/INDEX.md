# 知识库索引

> 最后更新：2026-10-09

## 0x01 项目知识

| 项目 | 路径 | 数量 | 说明 |
|------|------|------|------|
| ai-workspace | [ai-workspace/](./ai-workspace/INDEX.md) | 4 篇 | AI 工作区 — 知识管理与多项目协作中枢 |
| bk-cli | [bk-cli/](./bk-cli/INDEX.md) | 0 篇 | 蓝鲸平台 API 命令行工具 |
| bkmonitor | [bkmonitor/](./bkmonitor/INDEX.md) | 49 篇 | 蓝鲸监控平台（bk-monitor/bkmonitor） |
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

- 2026-10-10：更新 [RUM 分层统一查询](./bkmonitor/issues/2026-08-07-rum-unified-query/README.md)（设计会话时间线 Builder，节点详情复用 Span Builder；View 停留时长徽标改用 `field_unit` 声明单位）
- 2026-10-09：更新 [RUM 分层统一查询](./bkmonitor/issues/2026-08-07-rum-unified-query/README.md)（Vital 与 Error 详情去掉耗时徽标，View 关联查询按 View ID 定位）
- 2026-09-29：更新 [RUM 分层统一查询](./bkmonitor/issues/2026-08-07-rum-unified-query/README.md)（View 加载时序补齐累计里程碑协议，Web Vitals 标记携带评级阈值；登记 Span 详情 PR，View 导航开始改取 `started_at`）
- 2026-09-29：更新 [APM 服务数据状态下沉到后台服务发现](./bkmonitor/issues/2026-09-16-apm-service-data-status-heartbeat/README.md)（请求侧 `have_data` 改为删除，不再换源）
- 2026-09-22：更新 [APM 服务数据状态下沉到后台服务发现](./bkmonitor/issues/2026-09-16-apm-service-data-status-heartbeat/README.md)（精简调研与开发方案，统一注脚和代码引用，明确日志标签与服务状态口径）
- 2026-09-21：更新 [APM Trace 写入 ES 字段类型冲突](./bkmonitor/troubleshooting/apm-trace-es-field-mapping-conflict.md)（在原有轮转脚本下方补充 APM 内置 ES 配置刷新脚本）
