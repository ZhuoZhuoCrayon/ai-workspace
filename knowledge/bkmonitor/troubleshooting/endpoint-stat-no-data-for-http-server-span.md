---
title: endpoint stat 查询指定 SpanName 无数据
tags: [apm, endpoint-stat, span-name, http-route, semconv, bug]
description: endpoint stat 仍依赖 http.url 等旧字段聚合，给定应用的 HTTP server span 仅上报 http.route 和 http.target，导致指定 span_name 有原始数据但 stat 无数据
created: 2026-04-16
updated: 2026-04-16
---

# endpoint stat 查询指定 SpanName 无数据

## 0x01 关键信息

### a. 现象

- 在 BKOP 的 endpoint stat 页面中，按指定 `service_name` 和 `span_name` 查询时无统计结果。
- 同一组过滤条件在 BKTE 原始 Span 查询中可以查到数据，说明不是链路原始数据缺失。

### b. 环境

- BKOP 侧排查 Trace：
  `app_name=bkmonitor_production`，
  `trace_id=5b2af7e688f5f557c227f0f83f28685a`。
- BKTE 侧原始数据样例：
  `app_name=v3_dev`，
  `service_name=osm`，
  `span_name=services.osm.ticket.views.TicketViewSet.access_business`。
- BKTE 侧验证时间窗：
  `2026-04-14 23:54:14` 到 `2026-04-15 23:54:14`，
  以及 BKOP Trace 内部实际使用的
  `2026-04-14 21:24:09` 到 `2026-04-15 21:24:09`。
- 受影响样例：
  - 应用：`v3_dev`
  - 服务：`osm`
  - SpanName：`services.osm.ticket.views.TicketViewSet.access_business`

### c. 结论

- endpoint stat 当前实现默认只统计带特定“请求内容”字段的 Span。
- 给定应用中的这批 HTTP server span 没有这些旧字段，因此在聚合前就被过滤掉了。
- 该问题和 OpenTelemetry 新旧 HTTP 语义约定切换有关，`http.url` 已经不再是稳定依赖字段。

## 0x02 endpoint stat 当前逻辑

- 入口在 `packages/apm_web/meta/resources.py` 的
  `QueryEndpointStatisticsResource`。
- 默认 `span_keys` 固定为以下 5 个字段：
  - `db.system`
  - `http.url`
  - `messaging.system`
  - `rpc.system`
  - `trpc.callee_method`
- `perform_request()` 会把这些字段转换成 `group_keys`，
  再调用 `api.apm_api.query_span(...)` 做聚合查询。
- API 侧 `apm/resources.py` 中的 `QuerySpanResource`
  会在带 `group_keys` 时转调
  `trace_datasource.query_span_with_group_keys(...)`。
- `apm/models/datasource.py` 中的
  `query_span_with_group_keys()` 会先构造：
  - `group_by`：按上面 5 个字段聚合。
  - `or_query`：要求这 5 个字段里至少有一个 `exists`。
- 聚合结果回到 `QueryEndpointStatisticsResource` 后，
  还会继续做一次筛选：
  如果当前 bucket 的 `key` 中没有非空值，
  直接 `continue` 丢弃。
- 对 HTTP 类结果，代码还会额外把 `http_url`
  拿去匹配 URI 规则，做一次归类展示。

## 0x03 该问题出现的原因

### a. 给定应用的 Span 数据形态不同

- 在 BKTE 原始 Span 查询中，
  `services.osm.ticket.views.TicketViewSet.access_business`
  这类 Span 可以稳定查到。
- 这些 Span 的关键属性主要是：
  - `attributes.http.route`
  - `attributes.http.target`
  - `resource.service.name`
  - `span_name`
- 这批 Span 不带以下字段：
  - `attributes.http.url`
  - `attributes.db.system`
  - `attributes.messaging.system`
  - `attributes.rpc.system`
  - `attributes.trpc.*`

### b. endpoint stat 的预过滤过窄

- 由于 `query_span_with_group_keys()` 的 `or_query`
  只认旧的 5 类分组字段，
  这批 HTTP server span 在进入聚合前就全部被过滤掉。
- 因此后续 ES / UnifyQuery 聚合返回 `hits_length=0`，
  页面上看到的就是“指定 SpanName 的 stat 无数据”。

### c. OpenTelemetry 语义约定已变化

- OpenTelemetry 当前规范中，
  `http.url` 已标记为 Deprecated，
  推荐改用 `url.full`。
- 对 HTTP server span，
  规范更推荐使用低基数的 `http.route`
  表达路由模板，而不是依赖完整 URL。
- 当前 BKOP endpoint stat 仍以 `http.url`
  作为 HTTP 聚合主字段，
  与给定应用的上报数据以及新语义约定已经脱节。

## 0x04 建议的修复方案

### a. 调整 HTTP 聚合主字段

- 将 HTTP 场景的主分组字段从 `http.url`
  调整为 `http.route`。
- `http.route` 不存在时，
  再按兼容顺序兜底：
  - `url.path`
  - `http.target`

### b. 做新旧 semconv 兼容

- 对外展示和内部查询同时兼容以下字段：
  - 新字段：`http.route`、`url.path`、`url.full`
  - 旧字段：`http.target`、`http.url`
- 兼容策略应区分“展示字段”和“聚合字段”：
  - 聚合优先低基数字段。
  - 高基数且可能带敏感参数的 `url.full`
    只建议作为排查辅助，不建议直接做 stat 分组。

### c. 放宽当前预过滤

- 不要把“必须存在固定分组字段之一”作为聚合前置条件。
- 更稳妥的做法有两种：
  - 按节点类别选择不同的候选分组字段。
  - 允许 bucket 全空时兜底回落到 `span_name`
    或推导出的 HTTP 路由摘要，而不是直接丢弃。

### d. 一并修正现有实现细节

- `trpc_callee_method` 的 exists 过滤当前检查的是
  `attributes.trpc.namespace`，
  和分组字段 `attributes.trpc.callee_method`
  本身不一致，建议顺手修正。
- HTTP URL 归类逻辑当前也建立在 `http_url` 之上，
  需要同步评估是否改为基于 `http.route`
  或兼容 `url.path` / `http.target`。

## 0x05 参考

- [OpenTelemetry HTTP 属性注册表](https://opentelemetry.io/docs/specs/semconv/registry/attributes/http/)
- [OpenTelemetry HTTP spans 语义约定](https://opentelemetry.io/docs/specs/semconv/http/http-spans/)
- `packages/apm_web/meta/resources.py`
- `apm/resources.py`
- `apm/models/datasource.py`
