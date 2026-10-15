# 知识库索引

> 最后更新：2026-10-15

## 0x01 项目知识

| 项目 | 路径 | 数量 | 说明 |
|------|------|------|------|
| ai-workspace | [ai-workspace/](./ai-workspace/INDEX.md) | 5 篇 | AI 工作区 — 知识管理与多项目协作中枢 |
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

- 2026-10-15：更新 [APM 服务数据状态下沉到后台服务发现](./bkmonitor/issues/2026-09-16-apm-service-data-status-heartbeat/README.md)（里程碑 1 补充已通过审查，版本锚点登记分支与 PR #12790）
- 2026-10-14：更新 [APM 服务数据状态下沉到后台服务发现](./bkmonitor/issues/2026-09-16-apm-service-data-status-heartbeat/README.md)（心跳观测到有效 `last_data_at` 时补齐 `source`；不创建节点、不刷新 `updated_at`，并登记后续实现锚点）
- 2026-10-14：更新 [指标元信息存储与 SaaS/APM 自定义指标改造](./bkmonitor/issues/2026-09-15-custom-metric-metadata/README.md)（重排完整方案对比：前置 S1～S3x 场景定义，按方案拆分规模与存储数据，并为 A～D 端到端压测补充读写动作与核心 SQL 模式）
- 2026-10-12：更新 [RUM 分层统一查询](./bkmonitor/issues/2026-08-07-rum-unified-query/README.md)（会话时间线支持按 `view_id` 查询单个 View）
- 2026-10-11：新增 [工作区跨主机一键初始化](./ai-workspace/issues/2026-10-11-workspace-portable-bootstrap/README.md)（注册表改为相对路径，私有数据迁入独立仓库，外部 skills 按锁文件固定版本，`make bootstrap` 只克隆缺失仓库并在本机生成 skills 链接）
