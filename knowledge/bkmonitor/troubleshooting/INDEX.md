# bkmonitor Troubleshooting 索引

| 文件 | 标签 | 摘要 | 更新日期 |
|------|------|------|---------|
| [APM Trace 写入 ES 字段类型冲突](./apm-trace-es-field-mapping-conflict.md) | `apm` `trace` `elasticsearch` `mapping` `attribute-filter` `as-string` `index-rollover` `normaltypevalueconfig` `all-app-config` | APM Trace 字段在 keyword/object 或 long/string 之间冲突时的定位与修复方法，覆盖独立 drop 止血和 APP 全量配置配合索引轮转的类型迁移 | 2026-07-19 |
| [0 点活动上线导致 RPC 指标 series 暴涨](./rpc-series-spike-on-activity-launch.md) | `apm` `rpc` `cardinality` `series-spike` `callee-container` `sum-without-ip` | 通过 ΔC 边对比、维度拆解与 VM 新增 series 验证，定位活动上线引发的 RPC 指标 series 暴涨，并区分业务新值驱动与高基数扇出乘子 | 2026-04-29 |
| [endpoint stat 查询指定 SpanName 无数据](./endpoint-stat-no-data-for-http-server-span.md) | `apm` `endpoint-stat` `span-name` `http-route` `semconv` `bug` | endpoint stat 仍依赖 http.url 等旧字段聚合，给定应用的 HTTP server span 仅上报 http.route 和 http.target，导致指定 span_name 有原始数据但 stat 无数据 | 2026-04-16 |
| [告警详情页 graph_panel 为空时接口报错](./alert-detail-empty-graph-panel.md) | `alert` `graph-panel` `detail` `null` `bug` | 某些告警本身没有图表时，AlertDetailResource 仍无判空清洗 graph_panel，导致详情接口报错 | 2026-04-15 |
| [服务关联索引集在日志检索页面部分缺失](./log-relation-index-set-missing.md) | `apm` `log-relation` `index-set` `bug` | process_service_relation 中 next() 只取首个匹配，导致多索引集只返回一个 | 2026-03-10 |
