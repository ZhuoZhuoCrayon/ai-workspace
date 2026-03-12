# bkmonitor Issues 索引


| 文件                                                                                                     | 标签                                                        | 摘要                                                      | 更新日期       |
|------|------|------|---------|
| [告警日志查询支持 Doris 数据源](./2026-03-12-log-query-doris-support/README.md) | `log` `unify-query` `doris` `data-source` | 根因在 UQ Doris 转换，_index 应映射为 *，bkmonitor 侧关闭该改动 | 2026-03-12 |
| [APM 支持应用级别配置](./2026-03-04-apm-app-level-config/README.md)                                            | `apm` `service-config` `log-relation` `code-redefine` `app-level`     | 将 APM 服务关联配置从纯服务粒度扩展到应用级别，支持跨服务共享与全局配置                   | 2026-03-08 |
| [日志 UnifyQuery 环境变量白名单与 query_string 增强](./2026-03-05-log-uq-env-whitelist-and-query-string/README.md) | `log` `unify-query` `data-source` `query-string` `config` | 为日志 UnifyQuery 灰度白名单增加环境变量配置层，并对齐日志平台 query_string 处理逻辑 | 2026-03-05 |
| [APM 支持跨应用共享数据源](./2026-03-03-apm-shared-datasource/README.md)                                         | `apm` `datasource` `es` `shared-storage`                  | 支持多 APM 应用复用同一数据源，压缩 ES 索引数量，降低数据链路资源消耗                 | 2026-03-03 |
| [日志数据源切换 unify-query](./2026-02-10-log-ds-to-unify-query/README.md)                                    | `log` `unify-query` `data-source`                         | 将日志查询数据源从原有实现切换到 unify-query 统一查询层                      | 2026-02-10 |


