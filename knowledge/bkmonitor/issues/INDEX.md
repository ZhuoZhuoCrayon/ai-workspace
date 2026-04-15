# bkmonitor Issues 索引


| 文件                                                                                                     | 标签                                                        | 摘要                                                      | 更新日期       |
|------|------|------|---------|
| [新版告警详情支持查看主机关联采集项日志](./2026-04-15-alert-detail-host-collector-log-relation/README.md) | `alert` `log` `host-target` `collector` `log-relation` | 在新版告警详情后端聚合主机关联采集项日志索引，复用旧版 listIndexByHost 逻辑并扩展 HostTarget 与 BaseK8STarget | 2026-04-15 |
| [APM 返回码重定义规则清空不生效](./2026-04-10-apm-code-redefine-clear-not-effective/README.md) | `apm` `code-redefine` `code-relabel` `config-refresh` | 修复 APM 返回码重定义在清空保存后未同步删除下游配置的问题 | 2026-04-10 |
| [APM 支持应用级别配置](./2026-03-04-apm-app-level-config/README.md)                                            | `apm` `service-config` `log-relation` `code-redefine` `code-remark` `app-level`     | 将 APM 服务关联配置与返回码备注从纯服务粒度扩展到应用级别，支持跨服务共享与全局配置                   | 2026-04-10 |
| [APM 策略模板下发更新不覆盖部分非管理配置](./2026-03-27-apm-strategy-template-no-overwrite/README.md) | `apm` `strategy` `template` `dispatch` | APM 策略模板下发更新时，不覆盖用户自定义的非管理配置项 | 2026-03-27 |
| [Tracing MCP 新增服务列表工具](./2026-03-24-tracing-mcp-service-list/README.md) | `apm` `tracing` `mcp` `service-list` `entity-set` | 为 Tracing MCP 新增服务列表查询接口，优化 EntitySet 及关联组件 | 2026-03-24 |
| [【告警中心】APM 应用/服务页面嵌入列表页支持](./2026-03-19-alert-apm-embedded-list/README.md) | `alert` `apm` `embedded-list` `frontend` | 告警中心列表页支持嵌入到 APM 应用/服务页面，提供关联告警的上下文查看能力 | 2026-03-19 |
| [告警日志查询支持 Doris 数据源](./2026-03-12-log-query-doris-support/README.md) | `log` `unify-query` `doris` `data-source` | 根因在 UQ Doris 转换，_index 应映射为 *，bkmonitor 侧关闭该改动 | 2026-03-12 |
| [日志 UnifyQuery 环境变量白名单与 query_string 增强](./2026-03-05-log-uq-env-whitelist-and-query-string/README.md) | `log` `unify-query` `data-source` `query-string` `config` | 为日志 UnifyQuery 灰度白名单增加环境变量配置层，并对齐日志平台 query_string 处理逻辑 | 2026-03-05 |
| [APM 支持跨应用共享数据源](./2026-03-03-apm-shared-datasource/README.md)                                         | `apm` `datasource` `es` `shared-storage`                  | 支持多 APM 应用复用同一数据源，压缩 ES 索引数量，降低数据链路资源消耗                 | 2026-03-03 |
| [日志数据源切换 unify-query](./2026-02-10-log-ds-to-unify-query/README.md)                                    | `log` `unify-query` `data-source`                         | 将日志查询数据源从原有实现切换到 unify-query 统一查询层                      | 2026-02-10 |
