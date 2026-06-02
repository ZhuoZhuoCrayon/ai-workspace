# bkmonitor 知识库

> 蓝鲸监控平台 (bk-monitor/bkmonitor)

## 0x01 索引

### a. Issues

| 需求 | 标签 | 状态 | 更新日期 |
|------|------|------|----------|
| [错误视图 tRPC 场景适配](./issues/2026-05-31-apm-error-view-trpc-adaptation/README.md) | `apm` `error-view` `trpc` `rpc` `exception-type` `scene-view` `code-remark` | 设计中 | 2026-06-02 |
| [APM 预计算适配共享数据源](./issues/2026-05-14-apm-precalc-shared-multi-app/README.md) | `apm` `pre-calculate` `shared-datasource` `multi-app` `bmw` | 实现中 | 2026-05-22 |
| [APM 支持跨应用共享数据源](./issues/2026-03-03-apm-shared-datasource/README.md) | `apm` `datasource` `es` `shared-storage` | 设计中 | 2026-05-14 |
| [APM Span 内置指标支持声明式引用](./issues/2026-05-07-apm-span-builtin-metric-declarative-reference/README.md) | `apm` `span` `metric-group` `trace` `unify-query` `declarative` | 新建 | 2026-05-07 |
| [优化 APM 日志关联列表关系查询长耗时](./issues/2026-05-06-apm-log-relation-list-uq-latency/README.md) | `apm` `log-relation` `relation-query` `unify-query` `latency` | 方案已确认 | 2026-05-08 |
| [优化首页 TraceID 全局搜索的预计算延迟](./issues/2026-05-02-overview-trace-id-low-latency-search/README.md) | `overview` `search` `apm` `trace` `pre-calculate` `low-latency` | PR Review 中 | 2026-05-06 |
| [优化 APM 接口统计偶现查询报错](./issues/2026-04-21-apm-endpoint-stat-hot-window-divide-by-zero/README.md) | `apm` `endpoint-stat` `hot-window` `aggregation` `bucket-inconsistency` | 设计中 | 2026-04-21 |
| [新版告警详情支持查看主机关联采集项日志](./issues/2026-04-15-alert-detail-host-collector-log-relation/README.md) | `alert` `log` `host-target` `collector` `log-relation` | 设计中 | 2026-04-15 |
| [APM 返回码重定义规则清空不生效](./issues/2026-04-10-apm-code-redefine-clear-not-effective/README.md) | `apm` `code-redefine` `code-relabel` `config-refresh` | 设计中 | 2026-05-24 |
| [APM 支持应用级别配置](./issues/2026-03-04-apm-app-level-config/README.md) | `apm` `service-config` `log-relation` `code-redefine` `code-remark` `app-level` | 设计中 | 2026-05-24 |
| [APM 策略模板下发更新不覆盖部分非管理配置](./issues/2026-03-27-apm-strategy-template-no-overwrite/README.md) | `apm` `strategy` `template` `dispatch` | 新建 | 2026-03-27 |
| [Tracing MCP 新增服务列表工具](./issues/2026-03-24-tracing-mcp-service-list/README.md) | `apm` `tracing` `mcp` `service-list` `entity-set` | 新建 | 2026-03-24 |
| [【告警中心】APM 应用/服务页面嵌入列表页支持](./issues/2026-03-19-alert-apm-embedded-list/README.md) | `alert` `apm` `embedded-list` `frontend` | 新建 | 2026-03-19 |
| [告警日志查询支持 Doris 数据源](./issues/2026-03-12-log-query-doris-support/README.md) | `log` `unify-query` `doris` `data-source` | 已关闭（UQ 侧修复） | 2026-03-12 |
| [日志 UnifyQuery 环境变量白名单与 query_string 增强](./issues/2026-03-05-log-uq-env-whitelist-and-query-string/README.md) | `log` `unify-query` `data-source` `query-string` `config` | 已实现 | 2026-03-05 |
| [日志数据源切换 unify-query](./issues/2026-02-10-log-ds-to-unify-query/README.md) | `log` `unify-query` `data-source` | 对账中 | 2026-02-10 |

### b. Troubleshooting

| 分类 | 路径 | 数量 | 说明 |
|------|------|------|------|
| 排障经验 | [troubleshooting/](./troubleshooting/INDEX.md) | 5 篇 | 问题排查与修复记录 |

### c. Snippets

代码片段集合，包含告警、APM、自定义上报等常用操作。

- [Snippets 索引](./snippets/INDEX.md) — 16 个代码片段
