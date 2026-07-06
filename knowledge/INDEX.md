# 知识库索引

> 最后更新：2026-07-02

## 0x01 项目知识

| 项目 | 路径 | 数量 | 说明 |
|------|------|------|------|
| ai-workspace | [ai-workspace/](./ai-workspace/INDEX.md) | 4 篇 | AI 工作区 — 知识管理与多项目协作中枢 |
| bkmonitor | [bkmonitor/](./bkmonitor/INDEX.md) | 42 篇 | 蓝鲸监控平台 (bk-monitor/bkmonitor) |
| bkm-skills | [bkm-skills/](./bkm-skills/INDEX.md) | 6 篇 | BlueKing Monitor Skills |
| bkmonitor_mcp | [bkmonitor_mcp/](./bkmonitor_mcp/INDEX.md) | 1 篇 | 蓝鲸监控 MCP Server |
| bkmonitor-datalink | [bkmonitor-datalink/](./bkmonitor-datalink/INDEX.md) | 3 篇 | 蓝鲸监控数据链路 |
| bkmonitor-ecosystem | [bkmonitor-ecosystem/](./bkmonitor-ecosystem/INDEX.md) | 0 篇 | 蓝鲸监控生态 SDK 与接入 demo（外部版） |
| crypto-python-sdk | [crypto-python-sdk/](./crypto-python-sdk/INDEX.md) | 0 篇 | BlueKing 轻量级密码学工具包，统一加解密抽象层 |
| throttled-py | [throttled-py/](./throttled-py/INDEX.md) | 8 篇 | High-performance Python rate limiting library |
| 通用知识 | [_shared/](./_shared/INDEX.md) | 1 篇 | 跨项目通用知识 |

## 0x02 最近更新

- 2026-07-02：新增 [APM Trace 写入 ES 字段类型冲突](./bkmonitor/troubleshooting/apm-trace-es-field-mapping-conflict.md) 至 bkmonitor troubleshooting（沉淀 transfer 日志查询模板和 NormalTypeValueConfig drop 止血脚本）
- 2026-06-30：更新 [优化告警详情主机日志关联准确性](./bkmonitor/issues/2026-04-15-alert-detail-host-collector-log-relation/README.md) 至 bkmonitor（写回 [TencentBlueKing/bk-monitor #11276](https://github.com/TencentBlueKing/bk-monitor/pull/11276) 已合入，标记 ✅ 里程碑 1 已合入，里程碑 2 待创建）
- 2026-06-29：更新 [APM 支持跨应用共享数据源](./bkmonitor/issues/2026-03-03-apm-shared-datasource/README.md) 至 bkmonitor（补充迁入 / 迁出可重入方案，明确独占链路备份、恢复和命令入口）
- 2026-06-28：下架 bkmonitor-datalink troubleshooting `collector-from-record-empty-net-host-ip.md`（沉淀价值不高，对应修复逻辑已在源码与测试中固化）
- 2026-06-28：迁移 [采集器排障常用命令](./bkmonitor-datalink/snippets/collector-troubleshooting-basic-commands.md) 至 bkmonitor-datalink snippets（从 bkmonitor troubleshooting 改归 datalink snippets，追加 OTLP HTTP traces 探针命令，标注 busybox 时间戳陷阱）
