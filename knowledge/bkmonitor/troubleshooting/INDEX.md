# bkmonitor Troubleshooting 索引

| 文件 | 标签 | 摘要 | 更新日期 |
|------|------|------|---------|
| [0 点活动上线导致 RPC 指标 series 暴涨](./rpc-series-spike-on-activity-launch.md) | `apm` `rpc` `cardinality` `series-spike` `callee-container` `sum-without-ip` | 通过 ΔC 边对比 + 维度拆解 + 隐藏维度识别，定位活动上线引发的 series 暴涨主凶为业务自定义 sum_without_ip_* 漏剥 callee_container | 2026-04-25 |
| [endpoint stat 查询指定 SpanName 无数据](./endpoint-stat-no-data-for-http-server-span.md) | `apm` `endpoint-stat` `span-name` `http-route` `semconv` `bug` | endpoint stat 仍依赖 http.url 等旧字段聚合，给定应用的 HTTP server span 仅上报 http.route 和 http.target，导致指定 span_name 有原始数据但 stat 无数据 | 2026-04-16 |
| [告警详情页 graph_panel 为空时接口报错](./alert-detail-empty-graph-panel.md) | `alert` `graph-panel` `detail` `null` `bug` | 某些告警本身没有图表时，AlertDetailResource 仍无判空清洗 graph_panel，导致详情接口报错 | 2026-04-15 |
| [采集器抓包常用命令](./collector-troubleshooting-basic-commands.md) | `collector` `tcpdump` `packet-capture` `pcap` | 记录采集器排障时常用的 tcpdump 抓包命令，以及关键参数含义 | 2026-04-10 |
| [服务关联索引集在日志检索页面部分缺失](./log-relation-index-set-missing.md) | `apm` `log-relation` `index-set` `bug` | process_service_relation 中 next() 只取首个匹配，导致多索引集只返回一个 | 2026-03-10 |
