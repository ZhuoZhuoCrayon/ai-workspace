# bkmonitor Issues 索引


| 文件                                                                                                     | 标签                                                        | 摘要                                                      | 更新日期       |
|------|------|------|---------|
| [RUM 分层统一查询](./2026-08-07-rum-unified-query/README.md) | `rum` `apm` `query` `span` `view` `session` `factory` `unify-query` | 用统一 Target 和查询基类承接 RUM 分层检索与 APM Trace 查询 | 2026-08-18 |
| [APM 跨应用 Trace 检索](./2026-07-31-apm-cross-app-trace-search/README.md) | `apm` `trace` `cross-app-search` `index-set` `bklog` `celery` `unify-query` | 通过 Trace 数据源域索引集聚合同域 APM Trace 数据源，让 Trace ID 可以跨应用检索 | 2026-08-06 |
| [日志、调用链与事件枚举值查询接入 UnifyQuery](./2026-07-31-enum-values-unify-query/README.md) | `unify-query` `enum-values` `dimension-query` `log` `trace` `event` | 让枚举值查询统一进入 UnifyQuery.query_dimensions，并复用数据查询的灰度路由 | 2026-07-31 |
| [日志 UnifyQuery 环境变量黑名单与 query_string 增强](./2026-03-05-log-uq-env-whitelist-and-query-string/README.md) | `log` `unify-query` `data-source` `query-string` `config` `blacklist` | 日志查询默认切换到 UnifyQuery，通过环境变量黑名单保留按业务回退能力，并对齐 query_string 处理逻辑 | 2026-07-21 |
| [APM 关联容器日志采集项慢接口优化](./2026-07-10-apm-k8s-log-relation-cache/README.md) | `apm` `log-relation` `k8s` `cache` `latency` `index-set` | 通过后台任务预缓存服务与 K8S 容器日志索引的关联关系，消除逐服务关系查询瓶颈 | 2026-07-17 |
| [APM Span 详情支持 Links 反向关联展示](./2026-06-04-apm-span-links-reverse-relation/README.md) | `apm` `span` `trace` `links` `relation` `otlp` | 通过 TraceID 和 SpanID 过滤正向与反向关联，并统一返回 OpenTelemetry Link 列表 | 2026-06-25 |
| [日志数据源切换前后保持原始日志结构一致](./2026-06-08-log-uq-object-structure-restore/README.md) | `log` `unify-query` `data-source` `object-field` | 让日志 UnifyQuery 返回的打平对象字段恢复为 ES 查询时期的原始结构 | 2026-06-08 |
| [主机场景容器事件关联准确性提升](./2026-06-03-alert-host-k8s-event-relation-accuracy/README.md) | `alert` `k8s-event` `host-target` `k8s-node` `scene-view` `unify-query` | 让主机与 K8S-NODE 告警按节点维度关联容器事件，避免跨节点 workload 事件混入并降低关联查询成本 | 2026-06-04 |
| [【告警中心】优化关联日志条件构造不准确的问题](./2026-06-04-alert-log-search-condition-accuracy/README.md) | `alert` `log` `log-relation` `query-string` `alert-drilling` `lucene` | 修复日志告警关联日志在 query_string 模式下忽略策略过滤条件，导致查询范围大于实际告警范围的问题 | 2026-06-04 |
| [错误视图 tRPC 场景适配](./2026-05-31-apm-error-view-trpc-adaptation/README.md) | `apm` `error-view` `trpc` `rpc` `exception-type` `scene-view` `code-remark` | 让 APM 错误视图在 tRPC/RPC 返回码错误中统一构造异常语义，并支持联动过滤与错误详情返回码备注展示 | 2026-06-08 |
| [APM 预计算适配共享数据源](./2026-05-14-apm-precalc-shared-multi-app/README.md) | `apm` `pre-calculate` `shared-datasource` `multi-app` `bmw` | 让单 BMW 预计算任务感知共享 data_id 下的多个应用，不破坏现有任务模型与持久化键 | 2026-05-22 |
| [APM 支持跨应用共享数据源](./2026-03-03-apm-shared-datasource/README.md)                                         | `apm` `datasource` `es` `shared-storage` `migration`      | 支持多 APM 应用复用同一数据源，压缩 ES 索引数量，降低数据链路资源消耗                 | 2026-07-23 |
| [APM Span 内置指标支持声明式引用](./2026-05-07-apm-span-builtin-metric-declarative-reference/README.md) | `apm` `span` `metric-group` `trace` `unify-query` `declarative` | 将 Trace 概览图的 Span 指标查询从手工参数拼接收敛为可复用的声明式指标算子 | 2026-05-07 |
| [优化首页 TraceID 全局搜索的预计算延迟](./2026-05-02-overview-trace-id-low-latency-search/README.md) | `overview` `search` `apm` `trace` `pre-calculate` `low-latency` | 双路径并行收集 Trace 命中，流式累计 TopK=3，并用绝对 5s deadline 收口 | 2026-07-24 |
| [优化 APM 接口统计偶现查询报错](./2026-04-21-apm-endpoint-stat-hot-window-divide-by-zero/README.md) | `apm` `endpoint-stat` `hot-window` `aggregation` `bucket-inconsistency` | 修复 APM endpoint 统计在热时间窗口内因聚合分桶不一致导致的接口报错 | 2026-04-21 |
| [优化告警详情主机日志关联准确性](./2026-04-15-alert-detail-host-collector-log-relation/README.md) | `alert` `log` `host-target` `collector` `log-relation` `accuracy` | 先修复日志类 HOST 告警的原始日志关联优先级，再接入主机关联采集项日志索引 | 2026-07-27 |
| [APM 返回码重定义规则清空不生效](./2026-04-10-apm-code-redefine-clear-not-effective/README.md) | `apm` `code-redefine` `code-relabel` `config-refresh` | 修复 APM 返回码重定义在清空保存后未同步删除下游配置的问题 | 2026-05-24 |
| [APM 支持应用级别配置](./2026-03-04-apm-app-level-config/README.md)                                            | `apm` `service-config` `log-relation` `code-redefine` `code-remark` `app-level`     | 将 APM 服务关联配置与返回码备注从纯服务粒度扩展到应用级别，支持跨服务共享与全局配置                   | 2026-05-24 |
| [APM 策略模板下发更新不覆盖部分非管理配置](./2026-03-27-apm-strategy-template-no-overwrite/README.md) | `apm` `strategy` `template` `dispatch` | APM 策略模板下发更新时，不覆盖用户自定义的非管理配置项 | 2026-03-27 |
| [Tracing MCP 新增服务列表工具](./2026-03-24-tracing-mcp-service-list/README.md) | `apm` `tracing` `mcp` `service-list` `entity-set` | 为 Tracing MCP 新增服务列表查询接口，优化 EntitySet 及关联组件 | 2026-03-24 |
| [【告警中心】APM 应用/服务页面嵌入列表页支持](./2026-03-19-alert-apm-embedded-list/README.md) | `alert` `apm` `embedded-list` `frontend` | 告警中心列表页支持嵌入到 APM 应用/服务页面，提供关联告警的上下文查看能力 | 2026-03-19 |
| [告警日志查询支持 Doris 数据源](./2026-03-12-log-query-doris-support/README.md) | `log` `unify-query` `doris` `data-source` | 根因在 UQ Doris 转换，_index 应映射为 *，bkmonitor 侧关闭该改动 | 2026-03-12 |
| [日志数据源切换 unify-query](./2026-02-10-log-ds-to-unify-query/README.md)                                    | `log` `unify-query` `data-source`                         | 将日志查询数据源从原有实现切换到 unify-query 统一查询层                      | 2026-06-08 |
