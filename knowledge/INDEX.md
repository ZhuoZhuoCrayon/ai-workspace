# 知识库索引

> 最后更新：2026-05-03

## 0x01 项目知识

| 项目 | 路径 | 数量 | 说明 |
|------|------|------|------|
| ai-workspace | [ai-workspace/](./ai-workspace/INDEX.md) | 4 篇 | AI 工作区 — 知识管理与多项目协作中枢 |
| bkmonitor | [bkmonitor/](./bkmonitor/INDEX.md) | 33 篇 | 蓝鲸监控平台 (bk-monitor/bkmonitor) |
| bkm-skills | [bkm-skills/](./bkm-skills/INDEX.md) | 6 篇 | BlueKing Monitor Skills |
| bkmonitor_mcp | [bkmonitor_mcp/](./bkmonitor_mcp/INDEX.md) | 1 篇 | 蓝鲸监控 MCP Server |
| bkmonitor-datalink | [bkmonitor-datalink/](./bkmonitor-datalink/INDEX.md) | 1 篇 | 蓝鲸监控数据链路 |
| throttled-py | [throttled-py/](./throttled-py/INDEX.md) | 6 篇 | High-performance Python rate limiting library |
| 通用知识 | [_shared/](./_shared/INDEX.md) | 1 篇 | 跨项目通用知识 |

## 0x02 最近更新

- 2026-05-03：新增
  [优化存储不可用时的异常处理](./throttled-py/issues/2026-05-03-store-unavailable-error-handling/README.md)
  至 throttled-py
  （统一存储异常包装语义，并补齐 Store / AtomicAction / Throttled 的源码级调研基线）
- 2026-05-02：新增
  [优化首页 TraceID 全局搜索的预计算延迟](./bkmonitor/issues/2026-05-02-overview-trace-id-low-latency-search/README.md)
  至 bkmonitor
  （在预计算路径外补一条直查 APM 应用原始 Trace 的快速通道，双轨竞速）
- 2026-05-01：更新
  [APM 支持应用级别配置](./bkmonitor/issues/2026-03-04-apm-app-level-config/README.md)
  至 bkmonitor
  （收口返回码备注服务视角优先级与 serializer 校验边界）
- 2026-04-30：更新
  [APM 支持跨应用共享数据源](./bkmonitor/issues/2026-03-03-apm-shared-datasource/README.md)
  至 bkmonitor
  （补充 shared Trace 查询改造方案，收口 `TraceQueryGuard` 与多 table 解包边界）
- 2026-04-29：更新
  [0 点活动上线导致 RPC 指标 series 暴涨](./bkmonitor/troubleshooting/rpc-series-spike-on-activity-launch.md)
  至 bkmonitor
  （追加 4 月 29 日 0 点 series 峰值归因，修正 `callee_container` 治理收益口径）
