# 知识库索引

> 最后更新：2026-05-25

## 0x01 项目知识

| 项目 | 路径 | 数量 | 说明 |
|------|------|------|------|
| ai-workspace | [ai-workspace/](./ai-workspace/INDEX.md) | 4 篇 | AI 工作区 — 知识管理与多项目协作中枢 |
| bkmonitor | [bkmonitor/](./bkmonitor/INDEX.md) | 36 篇 | 蓝鲸监控平台 (bk-monitor/bkmonitor) |
| bkm-skills | [bkm-skills/](./bkm-skills/INDEX.md) | 6 篇 | BlueKing Monitor Skills |
| bkmonitor_mcp | [bkmonitor_mcp/](./bkmonitor_mcp/INDEX.md) | 1 篇 | 蓝鲸监控 MCP Server |
| bkmonitor-datalink | [bkmonitor-datalink/](./bkmonitor-datalink/INDEX.md) | 1 篇 | 蓝鲸监控数据链路 |
| bkmonitor-ecosystem | [bkmonitor-ecosystem/](./bkmonitor-ecosystem/INDEX.md) | 0 篇 | 蓝鲸监控生态 SDK 与接入 demo（外部版） |
| throttled-py | [throttled-py/](./throttled-py/INDEX.md) | 7 篇 | High-performance Python rate limiting library |
| 通用知识 | [_shared/](./_shared/INDEX.md) | 1 篇 | 跨项目通用知识 |

## 0x02 最近更新

- 2026-05-25：新增 [bkmonitor-ecosystem](./bkmonitor-ecosystem/INDEX.md) 至 public 知识库（注册 GitHub 外部版项目，并与 private 内部版同名区分）
- 2026-05-24：更新
  [APM SaaS 配置](./bkmonitor/snippets/apm-saas-config.md)
  至 bkmonitor
  （合并返回码重定义与服务关联日志全量同步脚本，并从 private 迁出日志关联片段）
- 2026-05-22：更新
  [APM 预计算适配共享数据源](./bkmonitor/issues/2026-05-14-apm-precalc-shared-multi-app/README.md)
  至 bkmonitor
  （按 PR #1327 收敛 BMW 预计算共享数据源方案：以 `is_shared`、`BaseInfo.AppKey()` 和当前 Dispatcher 行为为准）
- 2026-05-22：更新
  [Grafana 仪表盘导入](./bkmonitor/snippets/grafana-dashboard.md)
  至 bkmonitor
  （补充 Django shell 批量导入 BKCI 仪表盘片段，并保留单业务快速导入示例）
- 2026-05-18：更新
  [APM 预计算适配共享数据源](./bkmonitor/issues/2026-05-14-apm-precalc-shared-multi-app/README.md)
  至 bkmonitor
  （收敛预计算应用上下文模型：`BaseInfo` 承载 token，并通过 `BaseInfo.AppKey()` 派生应用路由键）
- 2026-05-17：更新
  [Store 类型抽象边界优化](./throttled-py/issues/2026-05-06-store-typing-abstraction-refactor/README.md)
  至 throttled-py
  （完成 `Throttled` sync / async 组合状态分端持有，移除 `BaseThrottledMixin` 跨端泛型，并补齐 `typing_checks` 类型验收）
