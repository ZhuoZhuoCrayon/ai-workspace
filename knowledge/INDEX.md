# 知识库索引

> 最后更新：2026-05-17

## 0x01 项目知识

| 项目 | 路径 | 数量 | 说明 |
|------|------|------|------|
| ai-workspace | [ai-workspace/](./ai-workspace/INDEX.md) | 4 篇 | AI 工作区 — 知识管理与多项目协作中枢 |
| bkmonitor | [bkmonitor/](./bkmonitor/INDEX.md) | 35 篇 | 蓝鲸监控平台 (bk-monitor/bkmonitor) |
| bkm-skills | [bkm-skills/](./bkm-skills/INDEX.md) | 6 篇 | BlueKing Monitor Skills |
| bkmonitor_mcp | [bkmonitor_mcp/](./bkmonitor_mcp/INDEX.md) | 1 篇 | 蓝鲸监控 MCP Server |
| bkmonitor-datalink | [bkmonitor-datalink/](./bkmonitor-datalink/INDEX.md) | 1 篇 | 蓝鲸监控数据链路 |
| throttled-py | [throttled-py/](./throttled-py/INDEX.md) | 7 篇 | High-performance Python rate limiting library |
| 通用知识 | [_shared/](./_shared/INDEX.md) | 1 篇 | 跨项目通用知识 |

## 0x02 最近更新

- 2026-05-17：更新
  [Store 类型抽象边界优化](./throttled-py/issues/2026-05-06-store-typing-abstraction-refactor/README.md)
  至 throttled-py
  （完成 `Throttled` sync / async 组合状态分端持有，移除 `BaseThrottledMixin` 跨端泛型，并补齐 `typing_checks` 类型验收）
- 2026-05-15：更新
  [APM 预计算适配共享数据源](./bkmonitor/issues/2026-05-14-apm-precalc-shared-multi-app/README.md)
  至 bkmonitor
  （开始实现 BMW 单任务多应用窗口主链路，已落地 AppKey、Dispatcher 与 Prometheus handler 按应用路由）
- 2026-05-14：新增
  [APM 预计算适配共享数据源](./bkmonitor/issues/2026-05-14-apm-precalc-shared-multi-app/README.md)
  至 bkmonitor
  （从 `2026-03-03-apm-shared-datasource/PLAN.md` 的 `0x02.i` 拆出独立 issue，方案改为「单任务多应用窗口」）
- 2026-05-14：更新
  [APM 支持跨应用共享数据源](./bkmonitor/issues/2026-03-03-apm-shared-datasource/README.md)
  至 bkmonitor
  （复查 PR #10583 检索隔离收口，确认旧 review 线程已修复并完成 resolve）
- 2026-05-13：更新
  [Store 类型抽象边界优化](./throttled-py/issues/2026-05-06-store-typing-abstraction-refactor/README.md)
  至 throttled-py
  （将 `BaseStoreMixin` 收敛为 `StoreSpec` / `StoreValidationLogic`，并让 sync / async `BaseStore` 各自持有 backend 槽位）
