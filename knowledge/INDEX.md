# 知识库索引

> 最后更新：2026-10-23

## 0x01 项目知识

| 项目 | 路径 | 数量 | 说明 |
|------|------|------|------|
| ai-workspace | [ai-workspace/](./ai-workspace/INDEX.md) | 6 篇 | AI 工作区 — 知识管理与多项目协作中枢 |
| bk-cli | [bk-cli/](./bk-cli/INDEX.md) | 0 篇 | 蓝鲸平台 API 命令行工具 |
| bkmonitor | [bkmonitor/](./bkmonitor/INDEX.md) | 50 篇 | 蓝鲸监控平台（bk-monitor/bkmonitor） |
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

- 2026-10-23：更新 [通用聊天 Agent 桥接组件](./ai-workspace/issues/2026-10-17-agent-chat-bridge/README.md)（执行器与模型改为全局偏好，上下文仍按会话保留）
- 2026-10-21：更新 [APM 服务数据状态下沉到后台服务发现](./bkmonitor/issues/2026-09-16-apm-service-data-status-heartbeat/README.md)（应用信息、Apdex 与告警图移除探测 PR #12851 已合入）
- 2026-10-20：新增 [LLM 消息截断容错展示](./bkmonitor/issues/2026-10-20-llm-message-truncation/README.md)（用截断样例和现成方案对比说明修复方向，待验证）
- 2026-10-17：新增 [通用聊天 Agent 桥接组件](./ai-workspace/issues/2026-10-17-agent-chat-bridge/README.md)（完成本地组件、Codex 两轮恢复、自动化测试及组件快照 PreCI）
- 2026-10-16：更新 [RUM 分层统一查询](./bkmonitor/issues/2026-08-07-rum-unified-query/README.md)（补充 View 结束判定：页面关闭、`15 min` 无活动和 `4 h` 会话轮转）
