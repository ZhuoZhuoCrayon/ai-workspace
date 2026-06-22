# 知识库索引

> 最后更新：2026-06-22

## 0x01 项目知识

| 项目 | 路径 | 数量 | 说明 |
|------|------|------|------|
| ai-workspace | [ai-workspace/](./ai-workspace/INDEX.md) | 4 篇 | AI 工作区 — 知识管理与多项目协作中枢 |
| bkmonitor | [bkmonitor/](./bkmonitor/INDEX.md) | 42 篇 | 蓝鲸监控平台 (bk-monitor/bkmonitor) |
| bkm-skills | [bkm-skills/](./bkm-skills/INDEX.md) | 6 篇 | BlueKing Monitor Skills |
| bkmonitor_mcp | [bkmonitor_mcp/](./bkmonitor_mcp/INDEX.md) | 1 篇 | 蓝鲸监控 MCP Server |
| bkmonitor-datalink | [bkmonitor-datalink/](./bkmonitor-datalink/INDEX.md) | 2 篇 | 蓝鲸监控数据链路 |
| bkmonitor-ecosystem | [bkmonitor-ecosystem/](./bkmonitor-ecosystem/INDEX.md) | 0 篇 | 蓝鲸监控生态 SDK 与接入 demo（外部版） |
| crypto-python-sdk | [crypto-python-sdk/](./crypto-python-sdk/INDEX.md) | 0 篇 | BlueKing 轻量级密码学工具包，统一加解密抽象层 |
| throttled-py | [throttled-py/](./throttled-py/INDEX.md) | 8 篇 | High-performance Python rate limiting library |
| 通用知识 | [_shared/](./_shared/INDEX.md) | 1 篇 | 跨项目通用知识 |

## 0x02 最近更新

- 2026-06-22：更新 [bk-collector 自适应限流](./bkmonitor-datalink/issues/2026-06-10-collector-adaptive-throttling/README.md) 至 bkmonitor-datalink（记录 C 场景 `-c 26` 压测结果，补充本轮限流参数与 PromQL 口径结果）
- 2026-06-17：更新 [APM Span 详情支持 Links 反向关联展示](./bkmonitor/issues/2026-06-04-apm-span-links-reverse-relation/README.md) 至 bkmonitor（写回 PR #11110，记录符合预期的已知边界，并补充里程碑 2 前端展示方案）
- 2026-06-16：新增 [为什么我又写了一个 Python 限流库：throttled-py](./throttled-py/articles/2026-06-16-throttled-py-intro/README.md) 至 throttled-py（介绍限流的本质与现有 Python 库的不足，并给出 throttled-py 的核心功能与快速上手）
- 2026-06-12：新增 [crypto-python-sdk](./crypto-python-sdk/INDEX.md) 项目知识库（接入 BlueKing crypto-python-sdk 加密 SDK，建立项目知识库入口）
- 2026-06-10：更新 [日志 UnifyQuery 环境变量白名单与 query_string 增强](./bkmonitor/issues/2026-03-05-log-uq-env-whitelist-and-query-string/README.md) 至 bkmonitor（补充日志聚类表 `_clustered` 后缀统一走 UnifyQuery 的方案与验证结论）
