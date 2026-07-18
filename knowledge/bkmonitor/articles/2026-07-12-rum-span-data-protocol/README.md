---
title: RUM 数据协议
tags: [rum, span, metric, log, data-protocol, opentelemetry, web]
description: 归档 bkmonitor RUM Web 的 Resource、Span、Metric 和 Log 协议，供数据上报、字段消费和协议核对使用。
created: 2026-07-12
updated: 2026-07-18
---
本文记录 `@blueking/open-telemetry` 当前上报的 Resource、Span、Metric 和 Log 字段。

| 状态                                                             | 描述          |
| -------------------------------------------------------------- | ----------- |
| ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | 已上报，保持现状。   |
| ![Deprecated](https://img.shields.io/badge/-deprecated-red)    | 已上报，但需要废弃。  |
| ![Development](https://img.shields.io/badge/-development-blue) | 新补充或字段位置变更。 |

# Span

## 0x01 公共字段

### a. 顶层字段

| 字段               | 状态                                                         | 类型      | 描述                                                                             | 备注                                                                          |
| ---------------- | ---------------------------------------------------------- | ------- | ------------------------------------------------------------------------------ | --------------------------------------------------------------------------- |
| `time`           | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | 数据上报时间（毫秒时间戳字符串）                                                               | 【非上报字段】由接收链路自动补充。                                                           |
| `app_name`       | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | 应用名称                                                                           | 【非上报字段】由接收链路自动补充。                                                           |
| `bk_biz_id`      | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | 业务 ID                                                                          | 【非上报字段】由接收链路自动补充。                                                           |
| `trace_id`       | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | Trace ID                                                                       | --                                                                          |
| `trace_state`    | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | Trace 状态                                                                       | --                                                                          |
| `span_name`      | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | Span 名称                                                                        | --                                                                          |
| `span_id`        | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | Span ID                                                                        | --                                                                          |
| `parent_span_id` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | 父 Span ID                                                                      | --                                                                          |
| `status`         | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | Status  | Span 执行状态                                                                      | 包含 `code` 和 `message`。                                                      |
| `kind`           | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | enum    | [Span 类型](https://opentelemetry.io/zh/docs/concepts/signals/traces/#span-kind) | 枚举值：<br>- 未定义：0<br>- 内部调用：1<br>- 同步被调：2<br>- 同步主调：3<br>- 异步主调：4<br>- 异步被调：5 |
| `resource`       | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | object  | 资源信息                                                                           | 服务、环境、SDK 等描述信息。                                                            |
| `events`         | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | Event[] | 事件列表                                                                           | 异常详情和 Long Task 脚本明细通过 Span Event 承载。                                         |
| `links`          | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | Link[]  | [Span 链接](https://opentelemetry.io/docs/concepts/signals/traces/#span-links)   | 链接的存在是为了 Span 同其他 Span 建立关联，从而表明存在因果关系。                                     |
| `attributes`     | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | object  | 属性                                                                             | 浏览器、设备、网络、异常等各类语义标签和度量。                                                     |
| `start_time`     | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int     | 开始时间（微秒）                                                                       | --                                                                          |
| `end_time`       | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int     | 结束时间（微秒）                                                                       | --                                                                          |
| `elapsed_time`   | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int     | 耗时（微秒）                                                                         | --                                                                          |

### b. Status

| 字段               | 状态                                                         | 类型  | 描述   | 备注                                   |
| ---------------- | ---------------------------------------------------------- | --- | ---- | ------------------------------------ |
| `status.code`    | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 状态码  | 0（未设置）<br />1（正常）<br />2（异常）            |
| `status.message` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 状态描述 | 仅在 `status.code` == 2 时有值，正常 span 为空 |

---

## 0x02 Attributes

### a. 基础字段

| 字段                           | 状态                                                          | 类型  | 描述         | 备注                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ---------------------------- | ----------------------------------------------------------- | --- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `attributes.user.id`         | ![Stable](https://img.shields.io/badge/-stable-lightgreen)  | str | 用户 ID      | --                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `attributes.span_type`       |                                                             | str | Span 类型    | 枚举值：<br>- 文档加载：document<br>- 路由切换：route<br>- 静态资源与 HTTP / API：resource<br>- 长任务：longtask<br>- 用户交互：action<br>- Web 指标：vital<br>- 错误：error<br>- 自定义：custom                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `attributes.span_subtype`    |                                                             | str | Span 子类型   | 不同 `span_type` 具有不同的子类型：<br>[a] document<br>- 导航：navigate<br>[b] route<br>- pushState<br>- replaceState<br>- popstate<br>- hashchange<br>- manual<br>- bfCache<br>- sessionRenewal<br>[c] resource<br>- script<br>- link<br>- img<br>- css<br>- xml<br>- fetch<br>- xhr<br>- video<br>- audio<br>- iframe<br>- beacon<br>- other<br>[d] longtask<br>- long-animation-frame<br>- long-task<br>[e] action<br>- click<br>- custom<br>[f] vital<br>- lcp<br>- fcp<br>- cls<br>- inp<br>- ttfb<br>[g] error<br>- js<br>- promise<br>- resource_load<br>- blank_screen<br>- csp<br>[h] custom<br>- websocket<br>- <自定义> |
| `attributes.result`          |                                                             | str | 结果         | 枚举值：<br>- 成功：`success`<br>- 错误：`error`<br>- 超时：`timeout`<br>- 警告：`warning`<br><br>⚠️                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `attributes.error_type`      |                                                             | str | 错误类型       | 枚举值：<br/>- none<br/>- http_4xx<br/>- http_5xx<br/>- network_timeout<br/>- js<br/>- promise<br/>- resource_load<br/>- blank_screen<br/>- csp<br/>- slow<br/>- longtask_blocking<br/>- network<br/>- custom                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `attributes.trace_scene`     |                                                             | str | 追踪场景       | 枚举值：`page_load`、 `route_change`、`user_action`、`startup`。                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `attributes.os_name`         | ![Deprecated](https://img.shields.io/badge/-deprecated-red) | str | 操作系统名称     | 【重复】以 `attributes.user_agent.os.name` 为准。                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `attributes.status_class`    | ![Deprecated](https://img.shields.io/badge/-deprecated-red) | str | HTTP 状态码分类 | 如 `2xx`、`3xx`、`4xx`、`5xx`。<br><br>❌ SDK 不应该提供，如果后续需要高频获取，考虑预计算或实时聚合。                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `attributes.event_label`     | ![Deprecated](https://img.shields.io/badge/-deprecated-red) | str | 中文事件标签     | 如 `API 调用`/`错误`等。<br><br>❌  SDK 不应该提供中文名，另外这个字段看着也没啥用。                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `attributes.duration_bucket` | ![Deprecated](https://img.shields.io/badge/-deprecated-red) | str | 耗时分桶       | 如 `<100ms`、`100~500ms`、`500ms~2s`、`>2s`。<br><br>❌ 不需要，耗时分桶应该由后端支持。                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |

### b. [exception](https://opentelemetry.io/docs/specs/semconv/registry/attributes/exception/)

| 字段                                     | 状态                                                          | 类型      | 描述        | 备注                                                                   |
| -------------------------------------- | ----------------------------------------------------------- | ------- | --------- | -------------------------------------------------------------------- |
| `attributes.error.handled`             |                                                             | boolean | 错误是否被捕获   |                                                                      |
| `attributes.error.source`              |                                                             | str     | 错误来源      | 枚举值：<br/>- window.error（固定值）<br/>- resource<br/>- unhandledrejection |
| `attributes.error.window_occurrence_index` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 节流窗口内已上报错误的触发序号 | 总量使用 `browser.error.count` Metric。 |
| `attributes.exception.fingerprint`     | ![Deprecated](https://img.shields.io/badge/-deprecated-red) | str     | 异常指纹      | 用于聚合同类异常                                                             |
| `attributes.exception.message`         | ![Deprecated](https://img.shields.io/badge/-deprecated-red) | str     | 异常完整消息    |                                                                      |
| `attributes.exception.message_short`   | ![Deprecated](https://img.shields.io/badge/-deprecated-red) | str     | 异常简短消息    | 适合列表展示                                                               |
| `attributes.exception.stacktrace`      | ![Deprecated](https://img.shields.io/badge/-deprecated-red) | str     | 异常堆栈信息    |                                                                      |
| `attributes.exception.stack_top_frame` | ![Deprecated](https://img.shields.io/badge/-deprecated-red) | str     | 堆栈顶部帧     |                                                                      |
| `attributes.exception.type`            | ![Deprecated](https://img.shields.io/badge/-deprecated-red) | str     | 异常类型      |                                                                      |

### c. rum

| 字段                               | 类型      | 描述   | 备注                                                                                                                                          |
|----------------------------------|---------|------|---------------------------------------------------------------------------------------------------------------------------------------------|
| `attributes.rum.page.host`       | str     | 站点   | 例如 `https://example.com`                                                                                                                    |
| `attributes.rum.page.path`       | str     | 路径   | 例如 `/`                                                                                                                                      |
| `attributes.rum.navigation.type` | str     | 导航类型 | 仅 `span_type=vital` 上报该字段，枚举值：<br>- back-forward<br>- back-forward-cache<br>- navigate<br>- prerender<br>- reload<br>- restore<br>- unknown |
### d. [browser](https://opentelemetry.io/docs/specs/semconv/registry/attributes/browser/)

| 字段                                   | 类型  | 描述      | 备注                                                |
|--------------------------------------|-----|---------|---------------------------------------------------|
| `attributes.browser.screen.height`   | int | 屏幕尺寸的高度 | Aegis 使用 `sr = 1728 * 1117`。                      |
| `attributes.browser.screen.width`    | int | 屏幕尺寸的宽度 | --                                                |
| `attributes.browser.viewport.height` | int | 视口尺寸的高度 | Aegis 使用 `vp = 576 * 918`。                        |
| `attributes.browser.viewport.width`  | int | 视口尺寸的宽度 | --                                                |
### e. [device](https://opentelemetry.io/docs/specs/semconv/registry/attributes/device/)

| 字段                         | 类型  | 描述      | 备注                                                                              |
| -------------------------- | --- | ------- | ------------------------------------------------------------------------------- |
| `attributes.device.id`     | str | 设备标识    | [a] 如 `fd136680-a37b-45ea-80ee-365bfdc7f82e`。<br>[b] ⚠️ Aegis 使用 `fId` 获取浏览器指纹。 |
| `attributes.device.memory` | int | 内存（单位 G |                                                                                 |
### f. [network](https://opentelemetry.io/docs/specs/semconv/registry/attributes/network/)

| 字段                                        | 类型      | 描述           | 备注                                                                            |
|-------------------------------------------|---------|--------------|-------------------------------------------------------------------------------|
| 【新增】 `attributes.network.connection.type` | str     | 连接类型         | [a] 如 `wifi`。<br>[b] ⚠️ Aegis netType：`wifi`、`wired`、`2G`、`3G`、`5G`、`6G`，需对齐。 |
| `attributes.network.downlink`             | int     | 预估下行带宽（Mbps） | ❌ 没有使用场景且 Aegis 也未提供该字段，Span 包含过多数值字段时后续难以聚合。                                 |
| `attributes.network.effective_type`       | str     | 有效网络质量       | 如 `4g`、`slow-2g`。<br><br>❌ 删除，把 `connection.type` 准确上报，现在都是 `wifi`。           |
| `attributes.network.rtt`                  | int     | 往返时延（毫秒）     |                                                                               |
| `attributes.network.save_data`            | boolean | 用户是否开启省流量模式  |                                                                               |
| `attributes.network.connection_type`      | str     | 连接类型         | ❌ 已规范命名，删除。                                                                   |
| `attributes.network.protocol.name`        | str     | 应用层网络协议      | 仅 `websocket.connect` 存在，固定为 `websocket`。                                        |
### g. session

| 字段                              | 类型      | 描述     | 备注 |
|---------------------------------|---------|--------|----|
| `attributes.session.has_replay` | boolean | 是否回放   |    |
| `attributes.session.id`         | str     | 会话唯一标识 |    |

### h. target

| 字段                                | 类型  | 描述               | 备注 |
|-----------------------------------|-----|------------------|----|
| `attributes.target_domain`        | str | 目标域名             | Resource 或 WebSocket URL 可解析时存在。 |
| `attributes.target_label`         | str | 跨类型主标签，用于统一检索    | 插件能够提取主检索标签时存在。 |
| `attributes.target_path_template` | str | 目标低基数路径模板        | Resource URL 或 View 路径可归一时存在。 |
| `attributes.target_value`         | str / int / boolean | 主数值（状态码、耗时、字节数等） | 当前事件存在主数值时写入。 |
### i. view

| 字段                               | 类型  | 描述     | 备注                                         |
|----------------------------------|-----|--------|--------------------------------------------|
| `attributes.view.id`             | str | 视图 ID  |                                            |
| `attributes.view.name`           | str | 视图名称   | 默认使用路由分组，手动模式可指定。                         |
| `attributes.view.loading_type`   | str | 视图加载类型 | 枚举值：<br/>- route_change<br/>- initial_load<br/>- session_renewal<br/>- bf_cache |
| `attributes.view.url`            | str | 视图 URL |                                            |
| `attributes.view.url_path_group` | str | 视图路径分组 |                                            |
| `attributes.view.loading_time`   | number | 视图加载耗时（ms） | 加载时间计算完成后上报。                           |
| `attributes.view.loading_time.source` | str | 视图加载耗时来源 | 自动或手动。                                  |
| `attributes.view.first_byte`     | number | 首字节时间（ms） | 仅初始导航存在。                                |
| `attributes.view.dom_interactive` | number | DOM 可交互时间（ms） | 仅初始导航存在。                             |
| `attributes.view.dom_content_loaded` | number | DOMContentLoaded 时间（ms） | 仅初始导航存在。                    |
| `attributes.view.dom_complete`   | number | DOM Complete 时间（ms） | 仅初始导航存在。                           |
| `attributes.view.load_event`     | number | Load Event 时间（ms） | 仅初始导航存在。                              |

### j. resource

以下字段仅在 `span_name=browser.resource` 时存在。Fetch / XHR 和静态资源共用该 Span 名，通过
`attributes.resource.type` 区分来源。

| 字段                                           | 状态                                                         | 类型      | 描述                                                                            |
| -------------------------------------------- | ---------------------------------------------------------- | ------- | ----------------------------------------------------------------------------- |
| `attributes.resource.type`                   | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | 所有 Resource Span 均存在；常见值包括 `img`、`script`、`xhr`、`fetch`、`link`、`css`、`iframe` |
| `attributes.resource.url`                    | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | 资源 URL（已脱敏）                                                                   |
| `attributes.resource.method`                 | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | 仅 Fetch / XHR 存在                                                              |
| `attributes.resource.status_code`            | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int     | 仅 Fetch / XHR 获取到响应状态时存在                                                      |
| `attributes.resource.duration`               | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 仅静态资源存在，单位为毫秒；Fetch / XHR 使用 Span 原生耗时                                        |
| `attributes.resource.decoded_body_size`      | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int     | 浏览器提供 PerformanceResourceTiming 时存在，单位为字节                                     |
| `attributes.resource.encoded_body_size`      | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int     | 浏览器提供 PerformanceResourceTiming 时存在，单位为字节                                     |
| `attributes.resource.size`                   | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int     | 获取到传输大小时存在，单位为字节                                                              |
| `attributes.resource.protocol`               | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | 浏览器提供下一跳协议时存在，如 `h2`                                                          |
| `attributes.resource.cache.hit`              | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | boolean | 仅确认命中缓存时写入 `true`                                                             |
| `attributes.resource.delivery_type`          | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | 浏览器提供交付类型时存在，如 `cache`、`navigational-prefetch`                                |
| `attributes.resource.render_blocking_status` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | 浏览器提供渲染阻塞状态时存在，枚举值为 `blocking`、`non-blocking`                                 |
| `attributes.resource.redirect.start`         | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 发生重定向且时间有效时存在，单位为毫秒                                                           |
| `attributes.resource.redirect.duration`      | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 发生重定向且时间有效时存在，单位为毫秒                                                           |
| `attributes.resource.worker.start`           | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 经过 Service Worker 且时间有效时存在，单位为毫秒                                              |
| `attributes.resource.worker.duration`        | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 经过 Service Worker 且时间有效时存在，单位为毫秒                                              |
| `attributes.resource.dns.start`              | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 发生 DNS 查询且时间有效时存在，单位为毫秒                                                       |
| `attributes.resource.dns.duration`           | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 发生 DNS 查询且时间有效时存在，单位为毫秒                                                       |
| `attributes.resource.connect.start`          | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 发生 TCP 建连且时间有效时存在，单位为毫秒                                                       |
| `attributes.resource.connect.duration`       | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 发生 TCP 建连且时间有效时存在，单位为毫秒                                                       |
| `attributes.resource.ssl.start`              | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 发生 TLS 握手且时间有效时存在，单位为毫秒                                                       |
| `attributes.resource.ssl.duration`           | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 发生 TLS 握手且时间有效时存在，单位为毫秒                                                       |
| `attributes.resource.first_byte.start`       | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 浏览器提供首字节阶段时间时存在，单位为毫秒                                                         |
| `attributes.resource.first_byte.duration`    | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 浏览器提供首字节阶段时间时存在，单位为毫秒                                                         |
| `attributes.resource.download.start`         | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 浏览器提供下载阶段时间时存在，单位为毫秒                                                          |
| `attributes.resource.download.duration`      | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 浏览器提供下载阶段时间时存在，单位为毫秒                                                          |

### k. http

| 字段                                     | 状态                                                         | 类型  | 描述                                              |
| -------------------------------------- | ---------------------------------------------------------- | --- | ----------------------------------------------- |
| `attributes.http.request.method`       | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 仅 `browser.resource` 的 Fetch / XHR 请求存在，使用大写方法名 |
| `attributes.http.response.status_code` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | Resource 获取到 HTTP 响应状态时存在                       |

### l. url

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `attributes.url.full` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | Resource、Resource Error 或 `websocket.connect` 存在，内容已脱敏 |
| `attributes.url.previous` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | `browser.view` 存在，记录前一个 View URL |
| `attributes.url.scheme` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 仅 `websocket.connect` 存在，枚举值为 `ws`、`wss` |

### m. server

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `attributes.server.address` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | Resource 或 `websocket.connect` 的 URL 可解析出目标主机时存在 |
| `attributes.server.port` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | Resource URL 包含端口或接收链路能够推导端口时存在 |

### n. document

span_name 固定为 `browser.view`。

| 字段                             | 类型  | 描述            | 备注                                                                                                                                                                       |
|--------------------------------|-----|---------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `attributes.event.source`      | str | 导航事件来源        | 初始加载固定为 `load`。                                                                                                                                                  |
| `attributes.trace_scene`       | str | 追踪场景          | 枚举值：<br/>- page_load                                                                                                                                                     |
| `attributes.view.end_reason`   | str | 结束原因          | 枚举值：<br/>- load（实际永不出现）<br/>- pushState<br/>- replaceState<br/>- popstate<br/>- hashchange<br/>- shutdown<br/>当 span_name 为 `browser.view` 且该 view 被后续路由或 shutdown 结束时上报 |
| `attributes.document.referrer` | str | 文档 referrer   | 仅初始加载上报。                                                                                                                                                       |

### o. vital

| 字段                        | 类型  | 描述         | 备注                                                                    |
|---------------------------|-----|------------|-----------------------------------------------------------------------|
| `attributes.vital.id`     | str | Vital 唯一标识 |                                                                       |
| `attributes.vital.metric` | str | 指标名        | 枚举值：<br/>- cls<br/>- inp<br/>- lcp<br/>- fcp<br/>- ttfb<br/>术语介绍看下方表格 |
| `attributes.vital.rating` | str | 评级         | 枚举值：<br/>- good<br/>- needs-improvement<br/>- poor                    |
| `attributes.vital.value`  | number | 指标测量值      |                                                                       |

`attributes.vital.metric` 的枚举值术语介绍如下：

| 值    | 描述                                                                    | 备注                                        |
|------|-----------------------------------------------------------------------|-------------------------------------------|
| cls  | [累积布局偏移（Cumulative Layout Shift）](https://web.dev/articles/cls)       | 一个以用户为中心的重要指标，用于衡量视觉稳定性                   |
| inp  | [交互到下一次绘制（Interaction to Next Paint）](https://web.dev/articles/inp)   | 稳定的核心网页指标，使用 Event Timing API 中的数据来评估响应速度 |
| lcp  | [最大内容绘制（Largest Contentful Paint, LCP）](https://web.dev/articles/lcp) | Core Web Vital 中的一个重要且稳定的指标，用于衡量页面加载的速度。  |
| fcp  | [首次内容绘制（First Contentful Paint）](https://web.dev/articles/fcp)        | 是一项以用户为中心的重要指标，用于衡量用户感知的加载速度              |
| ttfb | [首字节时间（Time to First Byte）](https://web.dev/articles/ttfb)            | 是指从浏览器发起请求到接收到服务器返回第一个数据字节所经过的时间          |

- vital.metric=cls

| 字段                                          | 类型  | 描述             | 备注                                                                                                                              |
|---------------------------------------------|-----|----------------|---------------------------------------------------------------------------------------------------------------------------------|
| `attributes.vital.cls.largest_shift_target` | str | 最大布局偏移的目标元素选择器 | 高基数字段，如 `body > div#app > button`，CLS 偏移的最大贡献者的 DOM 路径                                                                          |
| `attributes.vital.cls.largest_shift_value`  | number | 最大单次布局偏移分值     | 该元素造成的单次最大偏移分数，注意这是"最大一次"的分数，不是 CLS 累积总分（总分在 vital.value 和 target_value 里）。值越小越好，接近 0 为优                                        |
| `attributes.vital.cls.load_state`           | str | 最大偏移发生时的页面     | 枚举值：<br/>- loading<br/>- dom-interactive<br/>- dom-content-loaded<br/>- complete<br/>用于判断 CLS 偏移发生在首屏哪个时期（体验越差时越可能在 loading 阶段） |

- vital.metric=inp

| 字段                                         | 类型  | 描述        | 备注                                                |
|--------------------------------------------|-----|-----------|---------------------------------------------------|
| `attributes.vital.inp.input_delay`         | number | 输入延迟（ms）  | 用户发起交互（如点击）到事件处理器开始执行的等待时间，反映主线程繁忙程度              |
| `attributes.vital.inp.interaction_target`  | str | 交互目标元素选择器 | 高基数字段，库提供的 DOM 选择器字符串，如 `body > div#app > button` |
| `attributes.vital.inp.interaction_type`    | str | 交互类型      | 用户触发方式，如 `pointer`、`keyboard`，说明 INP 由什么输入方式产生    |
| `attributes.vital.inp.presentation_delay`  | number | 呈现延迟（ms）  | 事件处理回调完成之后，到浏览器实际渲染下一帧的耗时，CSS/布局/重绘瓶颈看这里          |
| `attributes.vital.inp.processing_duration` | number | 处理耗时（ms）  | 事件处理回调（如 click handler）本身的执行时间，JS 逻辑过重时这个值会变大     |

- vital.metric=lcp

| 字段                                            | 类型     | 描述                  | 备注                                                                                                     |
| --------------------------------------------- | ------ | ------------------- | ------------------------------------------------------------------------------------------------------ |
| `attributes.vital.lcp.element_render_delay`   | number | LCP 元素的渲染阻塞延迟（ms）   | [a] LCP 元素资源加载完成后，到浏览器真正渲染该元素之间的等待时间<br/>[b] 主要由主线程阻塞（长任务/JS 执行）导致<br/>[c] 值越小越好                       |
| `attributes.vital.lcp.resource_load_duration` | number | LCP 资源加载耗时（ms）      | [a] LCP 元素依赖的外部资源（图片/字体等）从请求到下载完成的时间<br/>[b] 如果 LCP 是纯文本节点，此项可能缺失<br/>[c] 用于排查 CDN/网络/资源体积问题           |
| `attributes.vital.lcp.target`                 | str    | LCP 目标元素的 DOM 选择器   | 高基数字段，LCP 候选元素的 CSS 选择器路径，如 `html > body > div#hero > img`                                             |
| `attributes.vital.lcp.time_to_first_byte`     | number | LCP 发生前的 TTFB（ms）   | [a] 从导航开始到收到首字节的耗时<br/>[b] 这是 LCP 的"基座"——如果 TTFB 本身就很高，后面两段也会相应推迟<br/>[c] LCP ≈ TTFB + 资源加载耗时 + 元素渲染延迟 |
| `attributes.vital.lcp.url`                    | str    | LCP 元素对应资源 URL（已脱敏） | 高基数字段，LCP 为图片/背景图/视频海报等资源时，这里是该资源的地址；如果 LCP 是文本节点，此项缺失。用于定位是哪张图片拖慢了首屏                                  |

- vital.metric=fcp

| 字段                                        | 类型  | 描述                | 备注                                                                                                             |
|-------------------------------------------|-----|-------------------|----------------------------------------------------------------------------------------------------------------|
| `attributes.vital.fcp.load_state`         | str | FCP 发生时的页面加载阶段    | 枚举值：<br/>- loading<br/>- dom-interactive<br/>- dom-content-loaded<br/>- complete<br/>用于判断首次内容绘制发生在页面加载的哪个时期    |
| `attributes.vital.fcp.time_to_first_byte` | number | FCP 发生前的首字节时间（ms） | [a] 从导航开始到收到服务器首个响应字节的耗时<br/>[b] FCP 不可能早于 TTFB，此值揭示了"网络基座"耗时<br/>[c] 当 FCP 延迟过高时，若此值大说明是服务端/网络问题，若小则可能是前端渲染阻塞 |

- vital.metric=ttfb

| 字段                                          | 类型  | 描述                   | 备注                                                           |
|---------------------------------------------|-----|----------------------|--------------------------------------------------------------|
| `attributes.vital.ttfb.waiting_duration`    | number | 请求就绪后的等待耗时（ms）       | 主要包括重定向处理、Service Worker 启动处理、请求排队                           |
| `attributes.vital.ttfb.dns_duration`        | number | DNS 解析耗时（ms）         | 解析慢通常由 DNS 服务器延迟、复杂 CNAME 链或本地 DNS 缓存失效导致。多国/多地域部署时此值可能偏高    |
| `attributes.vital.ttfb.connection_duration` | number | TCP + TLS 连接建立耗时（ms） | 包含 TCP 三次握手和 TLS/SSL 协商。HTTPS 强制、TLS 1.3 升级、CDN 边缘节点距离都会影响此值 |
| `attributes.vital.ttfb.request_duration`    | number | 请求发送后等待首字节耗时（ms）     | 导航请求的发送报文极小，此值主要反映网络往返 RTT 与服务器从接到请求到吐出首字节的时间                |

### p. error

- span_subtype == js（span_name == browser.error）

| 字段                                       | 类型      | 描述        | 备注                                                                   |
|------------------------------------------|---------|-----------|----------------------------------------------------------------------|
| `attributes.error.handled`               | boolean | 错误是否被捕获   |                                                                      |
| `attributes.error.source`                | str     | 错误来源      | 枚举值：<br/>- window.error（固定值）<br/>- resource<br/>- unhandledrejection |
| `attributes.error.window_occurrence_index` | int   | 节流窗口内已上报错误的触发序号 | 总量使用 `browser.error.count` Metric。 |
| `attributes.error.cross_origin`          | boolean | 跨域脚本错误    | 条件字段：仅跨域脚本错误（消息为 `"Script error."` 且无 stack / filename）时存在           |
| `attributes.code.column`                 | int     | 代码列号      |                                                                      |
| `attributes.code.filepath`               | str     | 代码文件路径    |                                                                      |
| `attributes.code.lineno`                 | int     | 代码行号      |                                                                      |
| `attributes.exception.fingerprint`       | str     | 异常指纹      | 用于聚合同类异常                                                             |
| `attributes.exception.message_short`     | str     | 异常简短消息    | 适合列表展示                                                               |
| `attributes.exception.stack_top_frame`   | str     | 堆栈顶部帧     |                                                                      |
| `events.name`                            | str     | 事件名称      |                                                                      |
| `events.timestamp`                       | str     | 事件发生时间戳   |                                                                      |
| `events.attributes.exception.type`       | str     | 异常类型      |                                                                      |
| `events.attributes.exception.message`    | str     | 异常的简短消息   |                                                                      |
| `events.attributes.exception.stacktrace` | str     | 异常的堆栈信息   | 根据 error 实例提取，不一定存在                                                  |

- span_subtype == promise（span_name == browser.unhandledrejection）

| 字段                                       | 类型      | 描述        | 备注                                                                   |
|------------------------------------------|---------|-----------|----------------------------------------------------------------------|
| `attributes.error.handled`               | boolean | 错误是否被捕获   |                                                                      |
| `attributes.error.source`                | str     | 错误来源      | 枚举值：<br/>- window.error（固定值）<br/>- resource<br/>- unhandledrejection |
| `attributes.error.window_occurrence_index` | int   | 节流窗口内已上报错误的触发序号 | 总量使用 `browser.error.count` Metric。 |
| `attributes.exception.fingerprint`       | str     | 异常指纹      | 用于聚合同类异常                                                             |
| `attributes.exception.message_short`     | str     | 异常简短消息    | 适合列表展示                                                               |
| `attributes.exception.stack_top_frame`   | str     | 堆栈顶部帧     |                                                                      |
| `events.name`                            | str     | 事件名称      |                                                                      |
| `events.timestamp`                       | str     | 事件发生时间戳   |                                                                      |
| `events.attributes.exception.type`       | str     | 异常类型      |                                                                      |
| `events.attributes.exception.message`    | str     | 异常的简短消息   |                                                                      |
| `events.attributes.exception.stacktrace` | str     | 异常的堆栈信息   | 根据 error 实例提取，不一定存在                                                  |

- span_subtype == resource_load（span_name == browser.resource_error）

| 字段                                       | 类型      | 描述            | 备注                                                                   |
|------------------------------------------|---------|---------------|----------------------------------------------------------------------|
| `attributes.error.handled`               | boolean | 错误是否被捕获       |                                                                      |
| `attributes.error.source`                | str     | 错误来源          | 枚举值：<br/>- window.error（固定值）<br/>- resource<br/>- unhandledrejection |
| `attributes.error.window_occurrence_index` | int   | 节流窗口内已上报错误的触发序号 | 总量使用 `browser.error.count` Metric。 |
| `attributes.exception.fingerprint`       | str     | 异常指纹          | 用于聚合同类异常                                                             |
| `attributes.exception.message_short`     | str     | 异常简短消息        | 适合列表展示                                                               |
| `attributes.exception.stack_top_frame`   | str     | 堆栈顶部帧         |                                                                      |
| `attributes.html.tag`                    | str     | 关联 HTML 标签    | 资源类错误时出现，例如 `IMG`                                                    |
| `events.name`                            | str     | 事件名称          |                                                                      |
| `events.timestamp`                       | str     | 事件发生时间戳       |                                                                      |
| `events.attributes.exception.type`       | str     | 异常类型          |                                                                      |
| `events.attributes.exception.message`    | str     | 异常的简短消息       |                                                                      |
| `events.attributes.exception.stacktrace` | str     | 异常的堆栈信息       | 根据 error 实例提取，不一定存在                                                  |

- span_subtype == blank_screen（span_name == browser.blank_screen）

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `attributes.blank_screen.empty_ratio` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 有效样本中的空白比例 |
| `attributes.blank_screen.reason` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 枚举值：`empty_viewport`、`missing_root` |
| `attributes.blank_screen.root_selector` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 采样根选择器 |
| `attributes.blank_screen.root_found` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | boolean | 是否找到采样根元素 |
| `attributes.blank_screen.sample_count` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 采样点总数 |
| `attributes.blank_screen.valid_sample_count` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 有效采样数 |
| `attributes.blank_screen.empty_sample_count` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 空白采样数 |
| `attributes.blank_screen.ignored_sample_count` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | Loading 阶段忽略的采样数 |
| `attributes.blank_screen.center_element` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 视口中心元素选择器 |

- span_subtype == csp（span_name == csp.violation）

| 字段                                   | 类型     | 描述               | 备注 |
|--------------------------------------|--------|------------------|----|
| `attributes.csp.blocked_uri`         | str | 被拦截资源（URL 类值已脱敏） |    |
| `attributes.csp.violated_directive`  | str | 违反的指令            |    |
| `attributes.csp.effective_directive` | str | 生效的指令            |    |
| `attributes.csp.disposition`         | str | enforce / report |    |
| `attributes.csp.source_file`         | str | 触发脚本（已脱敏）        |    |
| `attributes.csp.line_number`         | int | 触发位置行号           |    |
| `attributes.csp.column_number`       | int | 触发位置列号           |    |
| `attributes.csp.status_code`         | int | 状态码              |    |
| `attributes.csp.fingerprint`         | str | 节流指纹（djb2 hash）  |    |
| `attributes.csp.window_occurrence_index` | int | 节流窗口内已上报 Span 的触发序号 | 总量使用 `browser.csp_violation.count` Metric。 |
| `attributes.csp.original_policy`     | str | 完整策略，仅窗口首条携带     |    |

### q. longtask

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `attributes.long_task.id` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 长任务或长动画帧 ID |
| `attributes.long_task.entry_type` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 枚举值：`long-animation-frame`、`long-task` |
| `attributes.long_task.start_time` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 相对 `performance.timeOrigin` 的开始时间（ms） |
| `attributes.long_task.duration` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 总耗时（ms） |
| `attributes.long_task.blocking_duration` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 主线程阻塞耗时（ms） |
| `attributes.long_task.is_frozen_frame` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | boolean | 是否达到冻结帧阈值 |
| `attributes.long_task.culprit` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 最重脚本、函数或归因来源 |
| `attributes.long_task.script.count` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | LoAF 脚本数量 |
| `attributes.long_task.first_ui_event_timestamp` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 首个 UI 事件时间（ms） |
| `attributes.long_task.render_start` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 渲染阶段开始时间（ms） |
| `attributes.long_task.style_and_layout_start` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 样式与布局阶段开始时间（ms） |
| `attributes.long_task.culprit.duration` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 最重脚本耗时（ms） |
| `attributes.long_task.culprit.forced_style_and_layout_duration` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 最重脚本强制样式与布局耗时（ms） |
| `attributes.long_task.culprit.function_name` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 最重脚本函数名 |
| `attributes.long_task.culprit.invoker_type` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 最重脚本调用方类型 |

Long Task 脚本明细通过 `events.name=long_task.script` 上报：

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `events.attributes.long_task.script.duration` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 脚本耗时（ms） |
| `events.attributes.long_task.script.execution_start` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 脚本执行开始时间（ms） |
| `events.attributes.long_task.script.forced_style_and_layout_duration` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 强制样式与布局耗时（ms） |
| `events.attributes.long_task.script.pause_duration` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 暂停耗时（ms） |
| `events.attributes.long_task.script.source_char_position` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 源码字符位置 |
| `events.attributes.long_task.script.start_time` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 脚本开始时间（ms） |
| `events.attributes.long_task.script.invoker` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 调用方 |
| `events.attributes.long_task.script.invoker_type` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 调用方类型 |
| `events.attributes.long_task.script.source_function_name` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 源函数名 |
| `events.attributes.long_task.script.source_url` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 已脱敏的脚本 URL |
| `events.attributes.long_task.script.window_attribution` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | Window 归因 |

### r. action

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `attributes.action.id` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str / str[] | Action Span 为字符串，关联 Span 为 Action ID 数组 |
| `attributes.action.type` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 动作类型 |
| `attributes.action.name` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 动作名称 |
| `attributes.action.target.name` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 目标元素名称 |
| `attributes.action.target.tag` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 目标元素标签 |
| `attributes.action.loading_time` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 点击后页面活动稳定耗时（ms） |
| `attributes.action.resource.count` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | Action 关联资源数 |
| `attributes.action.error.count` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | Action 关联错误数 |
| `attributes.action.long_task.count` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | Action 关联长任务数 |
| `attributes.action.frustration.type` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str[] | 枚举值：`rage_click`、`dead_click`、`error_click` |
| `attributes.action.frustration.count` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 挫败信号数量 |

### s. route

- span_name == browser.view

| 字段                           | 类型     | 描述      | 备注                                                                                                                                          |
|------------------------------|--------|---------|---------------------------------------------------------------------------------------------------------------------------------------------|
| `attributes.event.source`    | str | 路由事件来源  | 枚举值：<br/>- pushState<br/>- replaceState<br/>- popstate<br/>- hashchange                                                                     |
| `attributes.trace_scene`     | str | 追踪场景    | 枚举值：<br/>- route_change                                                                                                                     |
| `attributes.view.end_reason` | str | 结束原因    | 枚举值：<br/>- load（实际永不出现）<br/>- pushState<br/>- replaceState<br/>- popstate<br/>- hashchange<br/>- shutdown<br/>当该 view 被后续路由或 shutdown 结束时上报 |

### t. custom

`reportCustomEvent()` 产生 `custom.<name>` Span。`websocket.connect` 同属 `custom` 类型，但只使用公共
URL、Server、Network 和 Target 字段，不产生 `attributes.websocket.*` Span 属性。

| 字段                                        | 类型     | 描述                    | 备注          |
|-------------------------------------------|--------|-----------------------|-------------|
| `attributes.rum.custom.name`              | str | 自定义事件名称              | `reportCustomEvent()` |

# Resource

Span、Metric 和 Log 使用同一个 OpenTelemetry Resource。Resource 在 SDK 实例创建时确定，不随单次事件变化。

协议基线：

- 接入数据按 SDK `0.0.20`、Schema `2` 维护。
- 当前仓库包版本仍为 `0.0.16`，源码默认 Schema 仍为 `1`，发布时需要同步版本与 Schema 常量。

下表使用归一后的 `resource.<key>` 路径，OTLP/HTTP JSON 上报时编码为 `resource.attributes[]` KeyValue。

## 0x01 基础字段

| 字段                                                                                                                     | 状态                                                             | 类型   | 描述     | 备注                                              |
| ---------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- | ---- | ------ | ----------------------------------------------- |
| `resource.service.name`                                                                                                | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str  | 服务名    | --                                              |
| `resource.service.version`                                                                                             | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str  | 版本     | --                                              |
| [`resource.deployment.environment.name`](https://opentelemetry.io/docs/specs/semconv/resource/deployment-environment/) | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str  | 环境     | 推荐：`development`、`production`、`staging`、`test`。 |
| [`resource.telemetry.sdk.language`](https://opentelemetry.io/docs/specs/semconv/resource/#telemetry-sdk)               | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | enum | 语言     | 固定值 `webjs`。                                    |
| `resource.telemetry.sdk.name` *[1]*                                                                                    | ![Development](https://img.shields.io/badge/-development-blue) | str  | SDK 名称 | --                                              |
| `resource.telemetry.sdk.version`                                                                                       | ![Development](https://img.shields.io/badge/-development-blue) | str  | SDK 版本 | --                                              |
| `resource.rum.provider`                                                                                                | ![Deprecated](https://img.shields.io/badge/-deprecated-red)    | str  | 数据提供方  | ❌ 使用标准的 `sdk.name` 代替。<br>                      |
| `resource.rum.schema.version`                                                                                          | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str  | RUM Schema 版本 | 最新版本固定为 `2`。                                  |
| `resource.browser.name`                                                                                                | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str  | 浏览器名称  | 如 `Chrome`、`Edge`。                              |
| `resource.browser.version`                                                                                             | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str  | 浏览器版本  | 如 `150`。                                         |
| `resource.device.type`                                                                                                 | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str  | 设备类型   | 枚举值：`desktop`、`mobile`。                         |
| `resource.device.logical_processor_count`                                                                              | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | int  | 逻辑处理器数量 | 如 `14`。                                          |
| `resource.os.name`                                                                                                     | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str  | 操作系统名称 | 如 `macOS`、`Windows`、`Android`。                   |

*[1] `resource.telemetry.sdk.name`：`@blueking/open-telemetry`（蓝鲸 Otel SDK）｜aegis（Aegis SDK）。*

## 0x02 [User Agent](https://opentelemetry.io/docs/specs/semconv/registry/attributes/user-agent/)

| 字段 *[1]*                       | 状态                                                             | 类型  | 描述                        | 备注                             |
| ------------------------------ | -------------------------------------------------------------- | --- | ------------------------- | ------------------------------ |
| `resource.user_agent.name`     | ![Development](https://img.shields.io/badge/-development-blue) | str | 代理名称                      | 通常指的是浏览器的名称，如 `Chrome`、`Edge`。 |
| `resource.user_agent.version`  | ![Development](https://img.shields.io/badge/-development-blue) | str | 代理版本                      | 通常指的是浏览器的名称，如 `149`、`151`。     |
| `resource.user_agent.original` | ![Development](https://img.shields.io/badge/-development-blue) | str | 客户端发送的 HTTP `User-Agent`。 | 如：`"Mozilla/5.0 ..."`。         |
| `resource.user_agent.os.name`  | ![Development](https://img.shields.io/badge/-development-blue) | str | 操作系统名                     | 如 `macOS`、`Windows`、`Android`。 |

*[1] 从原 attributes 迁移，以上字段在 RUM 场景均为不可变属性，放到 resource 更合理。*

# Metric

Metric 使用 Delta 聚合，仅保留低基数维度。`session.id`、`view.id` 和 `action.id` 不进入指标维度。

## 0x01 公共字段

Metric 通过 OTLP/HTTP JSON 上报。下表使用以下路径简称：

- `scopeMetrics[]`：`resourceMetrics[].scopeMetrics[]`
- `metrics[]`：`scopeMetrics[].metrics[]`
- `dataPoints[]`：`metrics[].sum.dataPoints[]` 或 `metrics[].histogram.dataPoints[]`

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `resourceMetrics` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | object[] | OTLP Metric 请求根字段。 |
| `resourceMetrics[].resource` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | object | 公共资源信息，字段见「Resource」。 |
| `resourceMetrics[].scopeMetrics` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | object[] | 按 Instrumentation Scope 分组的指标集合。 |
| `scopeMetrics[].scope` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | object | Instrumentation Scope，当前固定包含 `name=bk-rum`。 |
| `scopeMetrics[].metrics` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | object[] | 当前 Scope 中的指标集合。 |
| `metrics[].name` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 指标名称，取值见「指标清单」。 |
| `metrics[].description` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | SDK 创建指标时设置的英文说明。 |
| `metrics[].unit` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 指标单位：无量纲指标使用 `1`，耗时使用 `ms`，字节数使用 `By`，未设置时为空字符串。 |
| `metrics[].sum` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | object | Counter 数据，Histogram 不使用该字段。 |
| `metrics[].sum.aggregationTemporality` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 固定为 `1`，表示 Delta 聚合。 |
| `metrics[].sum.isMonotonic` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | boolean | 固定为 `true`。 |
| `metrics[].histogram` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | object | Histogram 数据，Counter 不使用该字段。 |
| `metrics[].histogram.aggregationTemporality` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 固定为 `1`，表示 Delta 聚合。 |

### a. Data Point

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `dataPoints[].attributes` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | KeyValue[] | 指标维度，字段见「Attributes」。 |
| `dataPoints[].startTimeUnixNano` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | Delta 周期开始时间，使用十进制纳秒时间戳字符串。 |
| `dataPoints[].timeUnixNano` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 数据点采集时间，使用十进制纳秒时间戳字符串。 |
| `dataPoints[].asDouble` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | Counter 的增量值，当前内置 Counter 均使用 Double 类型。 |
| `dataPoints[].count` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | Histogram 的样本数量。 |
| `dataPoints[].sum` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | Histogram 的样本总和。 |
| `dataPoints[].min` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | Histogram 的最小样本值。 |
| `dataPoints[].max` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | Histogram 的最大样本值。 |
| `dataPoints[].bucketCounts` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int[] | Histogram 各分桶的样本数量。 |
| `dataPoints[].explicitBounds` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number[] | Histogram 的显式分桶边界。 |

## 0x02 指标清单

### a. Web Vitals

| 字段                           | 状态                                                         | 类型        | 描述                                |
| ---------------------------- | ---------------------------------------------------------- | --------- | --------------------------------- |
| `browser.web_vital.cls`      | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | Histogram | CLS 分布，单位为 `1`，每个 View 结束时记录一次。   |
| `browser.web_vital.duration` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | Histogram | FCP、INP、LCP 和 TTFB 耗时分布，单位为 `ms`。 |

### b. View

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `browser.view.loading_time` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | Histogram | View 加载耗时分布，单位为 `ms`，仅启用 View Loading Time 计算且成功得到最终值时记录。 |

### c. Blank Screen

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `browser.blank_screen.count` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | Counter | 确认白屏的次数，每个 View 最多增加 `1`。 |

### d. Error

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `browser.error.count` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | Counter | JS、Promise 和资源加载错误总数，在 Error Span 节流前累计。 |
| `browser.csp_violation.count` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | Counter | CSP 违规总数，在 CSP Span 节流前累计，仅启用 CSP Violation 插件时记录。 |

### e. Long Task

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `browser.long_task.count` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | Counter | Long Task 或 Long Animation Frame 的数量，仅启用 Long Task 插件时记录。 |
| `browser.long_task.duration` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | Histogram | Long Task 或 Long Animation Frame 的总耗时分布，单位为 `ms`。 |
| `browser.long_task.blocking_duration` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | Histogram | Long Animation Frame 的阻塞耗时分布，单位为 `ms`，普通 Long Task 不记录。 |

### f. WebSocket

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `browser.websocket.message.count` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | Counter | WebSocket 收发消息数，仅启用 WebSocket 插件时记录。 |
| `browser.websocket.message.bytes` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | Counter | WebSocket 收发字节数，单位为 `By`，大于 `64 KB` 的字符串使用字符长度估算。 |
| `browser.websocket.error.count` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | Counter | WebSocket 建连或运行时错误数，不受错误日志节流影响。 |
| `browser.websocket.connect.duration` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | Histogram | WebSocket 成功建连耗时分布，单位为 `ms`，建连失败不记录。 |

### g. Histogram 分桶

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `browser.web_vital.cls` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number[] | 分桶边界为 `[0, 0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.25, 0.5, 1]`。 |
| `*.duration` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number[] | 所有时长 Histogram 共用 `[0, 50, 100, 200, 300, 500, 800, 1000, 1500, 2000, 2500, 4000, 5000, 10000]`，单位为 `ms`。 |

## 0x03 Attributes

### a. 公共字段

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `attributes.view.url_path_group` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 低基数 View 路径模板：数字 ID、UUID 和长十六进制段归一为 `:id`。 |
| `attributes.<custom>` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | OTel Attribute | `context.attributes.metric` Hook 返回的自定义低基数维度。 |

### b. Web Vitals

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `attributes.rum.navigation.type` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 导航类型，如 `navigate`、`reload`、`back-forward-cache`。 |
| `attributes.vital.metric` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 指标类型：CLS 指标固定为 `cls`，Duration 指标为 `fcp`、`inp`、`lcp`、`ttfb`。 |
| `attributes.vital.rating` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 评级，枚举值为 `good`、`needs-improvement`、`poor`。 |

### c. View

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `attributes.view.loading_type` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | View 加载类型，枚举值为 `initial_load`、`route_change`、`session_renewal`、`bf_cache`。 |

### d. Blank Screen

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `attributes.blank_screen.reason` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 白屏原因，枚举值为 `empty_viewport`、`missing_root`。 |
| `attributes.blank_screen.root_selector` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 白屏检测使用的根元素选择器。 |

### e. Error

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `attributes.error.source` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 错误来源，枚举值为 `window.error`、`unhandledrejection`、`resource`。 |
| `attributes.error.subtype` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 错误子类型，枚举值为 `js`、`promise`、`resource_load`。 |

### f. CSP

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `attributes.csp.disposition` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | CSP 处理方式，枚举值为 `enforce`、`report`。 |
| `attributes.csp.effective_directive` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 实际生效并触发违规的 CSP 指令。 |

### g. Long Task

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `attributes.long_task.entry_type` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 枚举值为 `long-animation-frame`、`long-task`。 |

### h. WebSocket

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `attributes.network.protocol.name` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 固定值 `websocket`。 |
| `attributes.server.address` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | WebSocket URL 可解析时记录目标 Host。 |
| `attributes.url.scheme` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | WebSocket URL 协议，枚举值为 `ws`、`wss`。 |
| `attributes.websocket.direction` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 消息方向，枚举值为 `in`、`out`，仅消息数和字节数指标存在。 |
| `attributes.websocket.error.phase` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 错误阶段，枚举值为 `connect`、`runtime`，仅错误数指标存在。 |

# Log

错误主数据使用 Error Span。SDK 不会为同一个 JS、Promise、资源加载或 CSP 错误重复上报 Error Log。

## 0x01 公共字段

Log 通过 OTLP/HTTP JSON 上报。下表中 `scopeLogs[]` 表示 `resourceLogs[].scopeLogs[]`，
`logRecords[]` 表示 `scopeLogs[].logRecords[]`。

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `resourceLogs` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | object[] | OTLP Log 请求根字段。 |
| `resourceLogs[].resource` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | object | 公共资源信息，字段见「Resource」。 |
| `resourceLogs[].scopeLogs` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | object[] | 按 Instrumentation Scope 分组的日志集合。 |
| `scopeLogs[].scope` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | object | Instrumentation Scope，当前固定包含 `name=bk-rum`。 |
| `scopeLogs[].logRecords` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | object[] | 当前 Scope 中的日志记录。 |
| `logRecords[].timeUnixNano` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 事件发生时间，使用十进制纳秒时间戳字符串。 |
| `logRecords[].observedTimeUnixNano` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | OpenTelemetry Logger 观测到日志的时间。 |
| `logRecords[].traceId` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 关联 Trace ID，`browser.request.body` 显式关联请求 Span，其他日志不保证存在。 |
| `logRecords[].spanId` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 关联 Span ID，`browser.request.body` 显式关联请求 Span，其他日志不保证存在。 |
| `logRecords[].flags` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 关联 Trace 的采样标记，无 Trace 上下文时不存在。 |
| `logRecords[].severityNumber` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | INFO 固定为 `9`，ERROR 固定为 `17`。 |
| `logRecords[].severityText` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 日志级别文本，当前取值为 `INFO`、`ERROR`。 |
| `logRecords[].body` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | AnyValue | 字符串事件名以 `{ "stringValue": "<事件名>" }` 上报，取值见「事件清单」。 |
| `logRecords[].eventName` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 仅 View 和 Request Body Log 显式设置，值与 `body.stringValue` 相同。 |
| `logRecords[].attributes` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | KeyValue[] | 运行时上下文和事件专属字段。 |
| `logRecords[].droppedAttributesCount` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 被 OpenTelemetry 属性数量限制丢弃的字段数，默认值为 `0`。 |

## 0x02 事件清单

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `session.start` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | INFO：当前页面首次创建新 Session 时上报，复用其他页面创建的共享 Session 时不上报。 |
| `session.rotate` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | INFO：Session 因不活跃或达到最长生命周期而轮换时上报。 |
| `browser.view` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | INFO：View 创建、属性更新、加载时间计算完成或结束时上报快照。 |
| `browser.request.body` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 显式启用 Request Body 采集后上报：错误请求为 ERROR，`capture=all` 时成功请求为 INFO。 |
| `websocket.error` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | ERROR：WebSocket 建连或运行时错误，相同 URL 在 `60 s` 内最多上报 `5` 条。 |
| `websocket.close` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | INFO：WebSocket 关闭时上报关闭码、原因和是否正常关闭。 |

## 0x03 Attributes

### a. 运行时上下文

普通日志必须具有有效的 Session 和 View 上下文。`session.start` 允许在 View 建立前上报，
`session.rotate` 是否带 View 字段取决于轮换时的新 View 是否已经建立。

浏览器、设备和网络字段复用 Span Attributes 中对应主题的定义。Schema `2` 已迁移到 Resource 的不可变字段不再重复列出。

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `attributes.user.id` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 接入方设置的用户 ID，未设置时不存在。 |
| `attributes.session.id` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 日志所属 Session ID。 |
| `attributes.session.has_replay` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | boolean | 当前固定为 `false`。 |
| `attributes.view.id` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 日志所属 View ID，初始 `session.start` 不存在。 |
| `attributes.view.name` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | View 名称，初始 `session.start` 不存在。 |
| `attributes.view.url` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 已脱敏的 View URL，初始 `session.start` 不存在。 |
| `attributes.view.url_path_group` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | View 低基数路径模板，初始 `session.start` 不存在。 |
| `attributes.view.loading_type` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | View 加载类型，初始 `session.start` 不存在。 |
| `attributes.action.id` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str[] | 日志发生在自动 Action 活跃期间时，记录关联的 Action ID。 |
| `attributes.rum.page.host` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 默认页面 Hook 生成的站点，仅 Session、View 和 Request Body Log 使用。 |
| `attributes.rum.page.path` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 默认页面 Hook 生成的路径，仅 Session、View 和 Request Body Log 使用。 |
| `attributes.<custom>` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | OTel Attribute | 页面 Hook、自定义 View 属性或事件扩展字段。 |

### b. Session

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `attributes.session.start_time` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | Session 开始时间，单位为毫秒时间戳。 |
| `attributes.session.previous_id` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 轮换前的 Session ID，仅 `session.rotate` 存在。 |
| `attributes.session.rotate.reason` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | `session.start` 固定为 `init`，`session.rotate` 为 `inactivity`、`maxLifetime`。 |

### c. View Snapshot

`browser.view` 继承同一个 View Span 的 Attributes，并补充以下快照字段。

| 字段                                    | 状态                                                         | 类型      | 描述                                   |
| ------------------------------------- | ---------------------------------------------------------- | ------- | ------------------------------------ |
| `attributes.event.type`               | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | 固定值 `view`。                          |
| `attributes.view.snapshot.type`       | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | 快照类型，枚举值为 `create`、`update`、`final`。 |
| `attributes.view.document_version`    | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int     | 当前 View 快照版本，从 `1` 开始递增。             |
| `attributes.view.duration`            | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 从 View 开始到本次快照的持续时间，单位为 `ms`。        |
| `attributes.view.is_active`           | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | boolean | `final` 快照为 `false`，其他快照为 `true`。    |
| `attributes.view.loading_time`        | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | View 加载耗时，单位为 `ms`，计算完成后才存在。         |
| `attributes.view.loading_time.source` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | 加载耗时来源，枚举值为 `auto`、`manual`。         |
| `attributes.view.end_reason`          | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | View 结束原因，仅 `final` 快照存在。            |

### d. Request Body

`browser.request.body` 继承对应 Resource Span 的 HTTP、Resource 和归一字段，并补充以下正文快照字段。

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `attributes.request.body` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 脱敏后的请求正文，只支持允许的文本 Content-Type。 |
| `attributes.request.body.content_type` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 请求正文 Content-Type，可获取时存在。 |
| `attributes.request.body.truncated` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | boolean | 请求正文是否因长度限制被截断。 |
| `attributes.response.body` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 脱敏后的响应正文，只支持允许的文本 Content-Type。 |
| `attributes.response.body.content_type` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 响应正文 Content-Type，可获取时存在。 |
| `attributes.response.body.truncated` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | boolean | 响应正文是否因长度限制被截断。 |

### e. WebSocket

WebSocket Log 使用 Span 中定义的 URL、Server、Network 和归一字段，并补充以下事件专属字段。

| 字段 | 状态 | 类型 | 描述 |
| --- | --- | --- | --- |
| `attributes.websocket.error.phase` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 错误阶段，枚举值为 `connect`、`runtime`，仅 `websocket.error` 存在。 |
| `attributes.websocket.error.window_occurrence_index` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 当前节流窗口内已上报错误日志的触发序号。 |
| `attributes.websocket.close.code` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | WebSocket 关闭码，仅 `websocket.close` 存在。 |
| `attributes.websocket.close.reason` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | WebSocket 关闭原因，仅 `websocket.close` 存在。 |
| `attributes.websocket.close.was_clean` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | boolean | 是否正常关闭，仅 `websocket.close` 存在。 |
