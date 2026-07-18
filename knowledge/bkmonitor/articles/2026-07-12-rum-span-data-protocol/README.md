---
title: RUM Span 数据协议
tags: [rum, span, data-protocol, opentelemetry, web]
description: 归档 bkmonitor RUM Web 的 Span 公共字段与各类型专属字段协议，供数据上报、字段消费和协议核对使用。
created: 2026-07-12
updated: 2026-07-12
---
# RUM Span 数据协议

| 状态                                                             | 描述          |
| -------------------------------------------------------------- | ----------- |
| ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | 已上报，保持现状。   |
| ![Deprecated](https://img.shields.io/badge/-deprecated-red)    | 已上报，但需要废弃。  |
| ![Development](https://img.shields.io/badge/-development-blue) | 新补充或字段位置变更。 |

## 0x01 公共字段

### a. 顶层字段

| 字段               | 状态                                                         | 类型      | 描述                                                                             | 备注                                                                          |
| ---------------- | ---------------------------------------------------------- | ------- | ------------------------------------------------------------------------------ | --------------------------------------------------------------------------- |
| `time`           | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int     | 数据上报时间（微秒）                                                                     | 【非上报字段】由接收链路自动补充。                                                           |
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
| `events`         | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | Event[] | 事件列表                                                                           | 数组，span_type 为 error 时存在。                                                   |
| `links`          | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | Link[]  | [Span 链接](https://opentelemetry.io/docs/concepts/signals/traces/#span-links)   | 链接的存在是为了 Span 同其他 Span 建立关联，从而表明存在因果关系。                                     |
| `attributes`     | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | object  | 属性                                                                             | 浏览器、设备、网络、异常等各类语义标签和度量。                                                     |
| `start_time`     | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int     | 开始时间（微秒）                                                                       | --                                                                          |
| `end_time`       | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int     | 结束时间（微秒）                                                                       | --                                                                          |
| `elapsed_time`   | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int     | 耗时（微秒）                                                                         | --                                                                          |
### b. [Resource](https://opentelemetry.io/docs/specs/semconv/resource/)

#### 1）基础字段

| 字段                                                                                                                     | 状态                                                             | 类型   | 描述     | 备注                                              |
| ---------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- | ---- | ------ | ----------------------------------------------- |
| `resource.service.name`                                                                                                | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str  | 服务名    | --                                              |
| `resource.service.version`                                                                                             | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str  | 版本     | --                                              |
| [`resource.deployment.environment.name`](https://opentelemetry.io/docs/specs/semconv/resource/deployment-environment/) | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str  | 环境     | 推荐：`development`、`production`、`staging`、`test`。 |
| [`resource.telemetry.sdk.language`](https://opentelemetry.io/docs/specs/semconv/resource/#telemetry-sdk)               | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | enum | 语言     | 固定值 `webjs`。                                    |
| `resource.telemetry.sdk.name` *[1]*                                                                                    | ![Development](https://img.shields.io/badge/-development-blue) | str  | SDK 名称 | --                                              |
| `resource.telemetry.sdk.version`                                                                                       | ![Development](https://img.shields.io/badge/-development-blue) | str  | SDK 版本 | --                                              |
| `resource.rum.provider`                                                                                                | ![Deprecated](https://img.shields.io/badge/-deprecated-red)    | str  | 数据提供方  | ❌ 使用标准的 `sdk.name` 代替。<br>                      |
*[1] `resource.telemetry.sdk.name`：blueking（蓝鲸 Otel SDK）｜aegis（Aegis SDK）。*

#### 2）[user_agent](https://opentelemetry.io/docs/specs/semconv/registry/attributes/user-agent/)

| 字段 *[1]*                       | 状态                                                             | 类型  | 描述                        | 备注                             |
| ------------------------------ | -------------------------------------------------------------- | --- | ------------------------- | ------------------------------ |
| `resource.user_agent.name`     | ![Development](https://img.shields.io/badge/-development-blue) | str | 代理名称                      | 通常指的是浏览器的名称，如 `Chrome`、`Edge`。 |
| `resource.user_agent.version`  | ![Development](https://img.shields.io/badge/-development-blue) | str | 代理版本                      | 通常指的是浏览器的名称，如 `149`、`151`。     |
| `resource.user_agent.original` | ![Development](https://img.shields.io/badge/-development-blue) | str | 客户端发送的 HTTP `User-Agent`。 | 如：`"Mozilla/5.0 ..."`。         |
| `resource.user_agent.os.name`  | ![Development](https://img.shields.io/badge/-development-blue) | str | 操作系统名                     | 如 `macOS`、`Windows`、`Android`。 |
*[1]  从原 attributes 迁移，以上字段在 RUM 场景均为不可变属性，放到 resource 更合理。*

### b. Attributes

#### 1）基础字段

| 字段                           | 状态                                                          | 类型  | 描述         | 备注                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ---------------------------- | ----------------------------------------------------------- | --- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `attributes.user.id`         | ![Stable](https://img.shields.io/badge/-stable-lightgreen)  | str | 用户 ID      | --                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `attributes.span_type`       |                                                             | str | Span 类型    | 枚举值：<br>- 文档加载：document<br>- 路由切换：route<br>- 静态资源：resource<br>- HTTP / API：http<br>- 长任务：longtask<br>- 用户交互：action<br>- Web 指标：vital<br>- 错误：error<br>- 自定义：custom                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `attributes.span_subtype`    |                                                             | str | Span 子类型   | 不同 `span_type` 具有不同的子类型：<br>[a] document<br>- 导航：navigate<br>- 文档下载完成：document_fetch<br>[b] route<br>- 压栈：pushState<br>- 替换：replaceState<br>- 弹栈：popstate<br>- 哈希变化：hashchange<br>[c] resource<br>- script<br>- link<br>- img<br>- css<br>- xml<br>- httprequest<br>- fetch<br>- video<br>- audio<br>- iframe<br>- beacon<br>- other<br>[d] http<br>- fetch<br>- xhr<br>- beacon<br>- sendbeacon<br>[e] longtask<br>- 脚本执行：script<br>- 布局：layout<br>- 绘制：paint<br>- 未归因：unknown<br>[f] action<br>- 点击：click<br>- 输入：input<br>- keydown<br>- scroll<br>- pointerdown<br>- submit<br>- custom<br>[g] vital<br>- lcp<br>- fcp<br>- cls<br>- inp<br>- fid<br>- ttfb<br>[h] error<br>- js<br>- promise<br>- resource_load<br>- blank_screen<br>- csp<br>- network<br>- cors<br>- console<br>- custom<br>[i]  custom<br>- websocket<br>- <自定义> |
| `attributes.result`          |                                                             | str | 结果         | 枚举值：<br>- 成功：`success`<br>- 错误：`error`<br>- 超时：`timeout`<br>- 警告：`warning`<br><br>⚠️                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `attributes.error_type`      |                                                             | str | 错误类型       | 枚举值：<br/>- none<br/>- http_4xx<br/>- http_5xx<br/>- network_timeout<br/>- js<br/>- promise<br/>- resource_load<br/>- blank_screen<br/>- csp<br/>- slow<br/>- longtask_blocking<br/>- network<br/>- custom                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `attributes.trace_scene`     |                                                             | str | 追踪场景       | 枚举值：`page_load`、 `route_change`、`user_action`、`startup`。                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `attributes.os_name`         | ![Deprecated](https://img.shields.io/badge/-deprecated-red) | str | 操作系统名称     | 【重复】以 `attributes.user_agent.os.name` 为准。                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `attributes.status_class`    | ![Deprecated](https://img.shields.io/badge/-deprecated-red) | str | HTTP 状态码分类 | 如 `2xx`、`3xx`、`4xx`、`5xx`。<br><br>❌ SDK 不应该提供，如果后续需要高频获取，考虑预计算或实时聚合。                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `attributes.event_label`     | ![Deprecated](https://img.shields.io/badge/-deprecated-red) | str | 中文事件标签     | 如 `API 调用`/`错误`等。<br><br>❌  SDK 不应该提供中文名，另外这个字段看着也没啥用。                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `attributes.duration_bucket` | ![Deprecated](https://img.shields.io/badge/-deprecated-red) | str | 耗时分桶       | 如 `<100ms`、`100~500ms`、`500ms~2s`、`>2s`。<br><br>❌ 不需要，耗时分桶应该由后端支持。                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |

#### 2）[exception](https://opentelemetry.io/docs/specs/semconv/registry/attributes/exception/)

| 字段                                     | 状态                                                          | 类型      | 描述        | 备注                                                                   |
| -------------------------------------- | ----------------------------------------------------------- | ------- | --------- | -------------------------------------------------------------------- |
| `attributes.error.handled`             |                                                             | boolean | 错误是否被捕获   |                                                                      |
| `attributes.error.source`              |                                                             | str     | 错误来源      | 枚举值：<br/>- window.error（固定值）<br/>- resource<br/>- unhandledrejection |
| `attributes.error.window_count`        |                                                             | int     | 窗口级错误累计次数 |                                                                      |
| `attributes.exception.fingerprint`     | ![Deprecated](https://img.shields.io/badge/-deprecated-red) | str     | 异常指纹      | 用于聚合同类异常                                                             |
| `attributes.exception.message`         | ![Deprecated](https://img.shields.io/badge/-deprecated-red) | str     | 异常完整消息    |                                                                      |
| `attributes.exception.message_short`   | ![Deprecated](https://img.shields.io/badge/-deprecated-red) | str     | 异常简短消息    | 适合列表展示                                                               |
| `attributes.exception.stacktrace`      | ![Deprecated](https://img.shields.io/badge/-deprecated-red) | str     | 异常堆栈信息    |                                                                      |
| `attributes.exception.stack_top_frame` | ![Deprecated](https://img.shields.io/badge/-deprecated-red) | str     | 堆栈顶部帧     |                                                                      |
| `attributes.exception.type`            | ![Deprecated](https://img.shields.io/badge/-deprecated-red) | str     | 异常类型      |                                                                      |

### c. Status

| 字段               | 状态                                                         | 类型  | 描述   | 备注                                   |
| ---------------- | ---------------------------------------------------------- | --- | ---- | ------------------------------------ |
| `status.code`    | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 状态码  | 0（未设置）<br />1（正常）<br />2（异常）            |
| `status.message` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 状态描述 | 仅在 `status.code` == 2 时有值，正常 span 为空 |

---

## 0x02 Attributes

### a. rum

| 字段                               | 类型      | 描述   | 备注                                                                                                                                          |
|----------------------------------|---------|------|---------------------------------------------------------------------------------------------------------------------------------------------|
| `attributes.rum.sampled`         | boolean | 是否采样 | --                                                                                                                                          |
| `attributes.rum.page.host`       | str     | 站点   | 例如 `https://example.com`                                                                                                                    |
| `attributes.rum.page.path`       | str     | 路径   | 例如 `/`                                                                                                                                      |
| `attributes.rum.navigation.type` | str     | 导航类型 | 仅 `span_type=vital` 上报该字段，枚举值：<br>- back-forward<br>- back-forward-cache<br>- navigate<br>- prerender<br>- reload<br>- restore<br>- unknown |
### b. [browser](https://opentelemetry.io/docs/specs/semconv/registry/attributes/browser/)

| 字段                                   | 类型  | 描述      | 备注                                                |
|--------------------------------------|-----|---------|---------------------------------------------------|
| `attributes.browser.screen.height`   | int | 屏幕尺寸的高度 | Aegis 使用 `sr = 1728 * 1117`。                      |
| `attributes.browser.screen.width`    | int | 屏幕尺寸的宽度 | --                                                |
| `attributes.browser.viewport.height` | int | 视口尺寸的高度 | Aegis 使用 `vp = 576 * 918`。                        |
| `attributes.browser.viewport.width`  | int | 视口尺寸的宽度 | --                                                |
| `attributes.browser_name`            | str | 浏览器名称   | 如 `Chrome`、`Edge`。<br><br>❌ 复用 `user_agent` 业界规范。 |
| `attributes.browser_version`         | str | 浏览器版本   | 如 `149`、`151`。<br><br>❌ 复用 `user_agent` 业界规范。     |
### c. [device](https://opentelemetry.io/docs/specs/semconv/registry/attributes/device/)

| 字段                            | 类型      | 描述         | 备注                                                                              |
|-------------------------------|---------|------------|---------------------------------------------------------------------------------|
| `attributes.device.id`        | str     | 设备标识     ` | [a] 如 `fd136680-a37b-45ea-80ee-365bfdc7f82e`。<br>[b] ⚠️ Aegis 使用 `fId` 获取浏览器指纹。 |
| `attributes.device.cpu_cores` | int     | CPU 核心数    |                                                                                 |
| `attributes.device.memory`    | int     | 内存（单位 G    |                                                                                 |
| `attributes.device.mobile`    | boolean | 是否为移动设备    |                                                                                 |
| `attributes.device.platform`  | str     | 设备平台       | 如 `macOS`、`Windows`、`Android`。<br><br>❌ 复用 `user_agent`                         |
| `attributes.device_type`      | str     | 设备类型       | ❌ `attributes.device.mobile` 已能代                                                |
### d. [network](https://opentelemetry.io/docs/specs/semconv/registry/attributes/network/)

| 字段                                        | 类型      | 描述           | 备注                                                                            |
|-------------------------------------------|---------|--------------|-------------------------------------------------------------------------------|
| 【新增】 `attributes.network.connection.type` | str     | 连接类型         | [a] 如 `wifi`。<br>[b] ⚠️ Aegis netType：`wifi`、`wired`、`2G`、`3G`、`5G`、`6G`，需对齐。 |
| `attributes.network.downlink`             | int     | 预估下行带宽（Mbps） | ❌ 没有使用场景且 Aegis 也未提供该字段，Span 包含过多数值字段时后续难以聚合。                                 |
| `attributes.network.effective_type`       | str     | 有效网络质量       | 如 `4g`、`slow-2g`。<br><br>❌ 删除，把 `connection.type` 准确上报，现在都是 `wifi`。           |
| `attributes.network.rtt`                  | int     | 往返时延（毫秒）     |                                                                               |
| `attributes.network.save_data`            | boolean | 用户是否开启省流量模式  |                                                                               |
| `attributes.network.connection_type`      | str     | 连接类型         | ❌ 已规范命名，删除。                                                                   |
### e. session

| 字段                              | 类型      | 描述     | 备注 |
|---------------------------------|---------|--------|----|
| `attributes.session.has_replay` | boolean | 是否回放   |    |
| `attributes.session.id`         | str     | 会话唯一标识 |    |

### f. target

| 字段                                | 类型  | 描述               | 备注 |
|-----------------------------------|-----|------------------|----|
| `attributes.target_domain`        | str | 目标域名             |    |
| `attributes.target_label`         | str | 跨类型主标签，用于统一检索    |    |
| `attributes.target_path_template` | str | 目标低基数路径模板        |    |
| `attributes.target_value`         | int | 主数值（状态码、耗时、字节数等） |    |
### g. view

| 字段                               | 类型  | 描述     | 备注                                         |
|----------------------------------|-----|--------|--------------------------------------------|
| `attributes.view.id`             | str | 视图 ID  |                                            |
| `attributes.view.loading_type`   | str | 视图加载类型 | 枚举值：<br/>- route_change<br/>- initial_load |
| `attributes.view.url`            | str | 视图 URL |                                            |
| `attributes.view.url_path_group` | str | 视图路径分组 |                                            |
## 0x02 专属字段

`span_type` 有九种类型，分别为 `document`、`http`、`resource`、`vital`、`error`、`longtask`、`action`、`route`、
`custom`，
下面根据类型梳理对应的专属字段。

### a. document

一共有四种 span_name，分别为蓝鲸自研 pageView 插件上报的 `browser.view` 和 `browser.page_view`，OTel 官方插件上报的
`documentFetch` 和 `documentLoad`。

| 字段                             | 类型  | 描述            | 备注                                                                                                                                                                       |
|--------------------------------|-----|---------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `attributes.event.source`      | str | 导航事件来源        | 枚举值：<br/>- load<br/>仅当 span_name 为 `browser.view` 和 `browser.page_view` 时上报                                                                                              |
| `attributes.trace_scene`       | str | 追踪场景          | 枚举值：<br/>- page_load                                                                                                                                                     |
| `attributes.view.end_reason`   | str | 结束原因          | 枚举值：<br/>- load（实际永不出现）<br/>- pushState<br/>- replaceState<br/>- popstate<br/>- hashchange<br/>- shutdown<br/>当 span_name 为 `browser.view` 且该 view 被后续路由或 shutdown 结束时上报 |
| `attributes.url.full`          | str | 完整资源 URL（已脱敏） | 仅当 span_name 为 `documentFetch` 和 `documentLoad` 时上报                                                                                                                      |
| `attributes.url.previous`      | str | 上一页 URL       | 仅当 span_name 为 `browser.view` 和 `browser.page_view` 时上报                                                                                                                  |
| `attributes.document.referrer` | str | 文档 referrer   | 仅当 span_name 为 `browser.view` 和 `browser.page_view` 时上报                                                                                                                  |

### b. http（无数据上报，暂无法校验）

| 字段                                        | 类型      | 描述                     | 备注                                                                                             |
|-------------------------------------------|---------|------------------------|------------------------------------------------------------------------------------------------|
| `attributes.initiator_type`               | str     | 资源发起类型                 | 常见值：<br/>- img<br/>- script<br/>- xmlhttprequest<br/>- fetch<br/>- link<br/>- css<br/>- iframe |
| `attributes.http.request.method`          | str     | HTTP 请求方法（大写）          |                                                                                                |
| `attributes.http.response.status_code`    | int     | HTTP 响应状态码             |                                                                                                |
| `attributes.resource.decoded_body_size`   | int     | 解码后资源大小（字节）            |                                                                                                |
| `attributes.resource.encoded_body_size`   | int     | 编码后资源大小（字节）            |                                                                                                |
| `attributes.transfer_size`                | int     | 传输大小（字节数）              |                                                                                                |
| `attributes.url.full`                     | str     | 完整资源 URL（已脱敏）          |                                                                                                |
| `attributes.url.previous`                 | str     | 跳转前 URL                |                                                                                                |
| `attributes.target_domain`                | str     | 目标域名                   |                                                                                                |
| `attributes.target_path_template`         | str     | 目标路径模板                 |                                                                                                |
| `attributes.next_hop_protocol`            | str     | 下一跳协议                  | 例如 `h2` / `http/1.1`                                                                           |
| `attributes.cache_hit`                    | boolean | 是否命中缓存                 |                                                                                                |
| `attributes.http.duration`                | int     | httpBody 插件记录的请求耗时（ms） |                                                                                                |
| `attributes.http.request.body`            | str     |                        |                                                                                                |
| `attributes.http.response.body`           | str     |                        |                                                                                                |
| `attributes.http_body.request.truncated`  | boolean |                        |                                                                                                |
| `attributes.http_body.response.truncated` | boolean |                        |                                                                                                |

### c. resource

一共有两种 span_name，分别为蓝鲸自研 resource 插件上报的 `browser.resource`，OTel 官方插件上报的 `resourceFetch`。

| 字段                                      | 类型      | 描述            | 备注                                                                                                                                      |
|-----------------------------------------|---------|---------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| `attributes.initiator_type`             | str     | 资源发起类型        | 常见值：<br/>- img<br/>- script<br/>- xmlhttprequest<br/>- fetch<br/>- link<br/>- css<br/>- iframe<br/>仅当 span_name 为 `browser.resource` 存在 |
| `attributes.http.response.status_code`  | int     | HTTP 响应状态码    |                                                                                                                                         |
| `attributes.resource.decoded_body_size` | int     | 解码后资源大小（字节）   | 仅当 span_name 为 `browser.resource` 时存在                                                                                                   |
| `attributes.resource.encoded_body_size` | int     | 编码后资源大小（字节）   | 仅当 span_name 为 `browser.resource` 时存在                                                                                                   |
| `attributes.transfer_size`              | int     | 传输大小（字节数）     | 仅当 span_name 为 `browser.resource` 时存在                                                                                                   |
| `attributes.url.full`                   | str     | 完整资源 URL（已脱敏） |                                                                                                                                         |
| `attributes.target_domain`              | str     | 目标域名          |                                                                                                                                         |
| `attributes.target_path_template`       | str     | 目标路径模板        |                                                                                                                                         |
| `attributes.next_hop_protocol`          | str     | 下一跳协议         | 仅当 span_name 为 `browser.resource` 时存在                                                                                                   |
| `attributes.cache_hit`                  | boolean | 是否命中缓存        | 仅当 span_name 为 `browser.resource` 时存在                                                                                                   |

### d. vital

| 字段                        | 类型  | 描述         | 备注                                                                    |
|---------------------------|-----|------------|-----------------------------------------------------------------------|
| `attributes.vital.id`     | str | Vital 唯一标识 |                                                                       |
| `attributes.vital.metric` | str | 指标名        | 枚举值：<br/>- cls<br/>- inp<br/>- lcp<br/>- fcp<br/>- ttfb<br/>术语介绍看下方表格 |
| `attributes.vital.rating` | str | 评级         | 枚举值：<br/>- good<br/>- needs-improvement<br/>- poor                    |
| `attributes.vital.value`  | int | 指标测量值      |                                                                       |

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
| `attributes.vital.cls.largest_shift_value`  | int | 最大单次布局偏移分值     | 该元素造成的单次最大偏移分数，注意这是"最大一次"的分数，不是 CLS 累积总分（总分在 vital.value 和 target_value 里）。值越小越好，接近 0 为优                                        |
| `attributes.vital.cls.load_state`           | str | 最大偏移发生时的页面     | 枚举值：<br/>- loading<br/>- dom-interactive<br/>- dom-content-loaded<br/>- complete<br/>用于判断 CLS 偏移发生在首屏哪个时期（体验越差时越可能在 loading 阶段） |

- vital.metric=inp

| 字段                                         | 类型  | 描述        | 备注                                                |
|--------------------------------------------|-----|-----------|---------------------------------------------------|
| `attributes.vital.inp.input_delay`         | str | 输入延迟（ms）  | 用户发起交互（如点击）到事件处理器开始执行的等待时间，反映主线程繁忙程度              |
| `attributes.vital.inp.interaction_target`  | str | 交互目标元素选择器 | 高基数字段，库提供的 DOM 选择器字符串，如 `body > div#app > button` |
| `attributes.vital.inp.interaction_type`    | str | 交互类型      | 用户触发方式，如 `pointer`、`keyboard`，说明 INP 由什么输入方式产生    |
| `attributes.vital.inp.presentation_delay`  | int | 呈现延迟（ms）  | 事件处理回调完成之后，到浏览器实际渲染下一帧的耗时，CSS/布局/重绘瓶颈看这里          |
| `attributes.vital.inp.processing_duration` | int | 处理耗时（ms）  | 事件处理回调（如 click handler）本身的执行时间，JS 逻辑过重时这个值会变大     |

- vital.metric=lcp

| 字段                                            | 类型  | 描述                  | 备注                                                                                                     |
|-----------------------------------------------|-----|---------------------|--------------------------------------------------------------------------------------------------------|
| `attributes.vital.lcp.element_render_delay`   | int | LCP 元素的渲染阻塞延迟（ms）   | [a] LCP 元素资源加载完成后，到浏览器真正渲染该元素之间的等待时间<br/>[b] 主要由主线程阻塞（长任务/JS 执行）导致<br/>[c] 值越小越好                       |
| `attributes.vital.lcp.resource_load_duration` | int | LCP 资源加载耗时（ms）      | [a] LCP 元素依赖的外部资源（图片/字体等）从请求到下载完成的时间<br/>[b] 如果 LCP 是纯文本节点，此项可能缺失<br/>[c] 用于排查 CDN/网络/资源体积问题           |
| `attributes.vital.lcp.target`                 | str | LCP 目标元素的 DOM 选择器   | 高基数字段，LCP 候选元素的 CSS 选择器路径，如 `html > body > div#hero > img`                                             |
| `attributes.vital.lcp.time_to_first_byte`     | int | LCP 发生前的 TTFB（ms）   | [a] 从导航开始到收到首字节的耗时<br/>[b] 这是 LCP 的"基座"——如果 TTFB 本身就很高，后面两段也会相应推迟<br/>[c] LCP ≈ TTFB + 资源加载耗时 + 元素渲染延迟 |
| `attributes.vital.lcp.url`                    | str | LCP 元素对应资源 URL（已脱敏） | 高基数字段，LCP 为图片/背景图/视频海报等资源时，这里是该资源的地址；如果 LCP 是文本节点，此项缺失。用于定位是哪张图片拖慢了首屏                                  |

- vital.metric=fcp

| 字段                                        | 类型  | 描述                | 备注                                                                                                             |
|-------------------------------------------|-----|-------------------|----------------------------------------------------------------------------------------------------------------|
| `attributes.vital.fcp.load_state`         | str | FCP 发生时的页面加载阶段    | 枚举值：<br/>- loading<br/>- dom-interactive<br/>- dom-content-loaded<br/>- complete<br/>用于判断首次内容绘制发生在页面加载的哪个时期    |
| `attributes.vital.fcp.time_to_first_byte` | int | FCP 发生前的首字节时间（ms） | [a] 从导航开始到收到服务器首个响应字节的耗时<br/>[b] FCP 不可能早于 TTFB，此值揭示了"网络基座"耗时<br/>[c] 当 FCP 延迟过高时，若此值大说明是服务端/网络问题，若小则可能是前端渲染阻塞 |

- vital.metric=ttfb

| 字段                                          | 类型  | 描述                   | 备注                                                           |
|---------------------------------------------|-----|----------------------|--------------------------------------------------------------|
| `attributes.vital.ttfb.waiting_duration`    | int | 请求就绪后的等待耗时（ms）       | 主要包括重定向处理、Service Worker 启动处理、请求排队                           |
| `attributes.vital.ttfb.dns_duration`        | int | DNS 解析耗时（ms）         | 解析慢通常由 DNS 服务器延迟、复杂 CNAME 链或本地 DNS 缓存失效导致。多国/多地域部署时此值可能偏高    |
| `attributes.vital.ttfb.connection_duration` | int | TCP + TLS 连接建立耗时（ms） | 包含 TCP 三次握手和 TLS/SSL 协商。HTTPS 强制、TLS 1.3 升级、CDN 边缘节点距离都会影响此值 |
| `attributes.vital.ttfb.request_duration`    | int | 请求发送后等待首字节耗时（ms）     | 导航请求的发送报文极小，此值主要反映网络往返 RTT 与服务器从接到请求到吐出首字节的时间                |

### e. error

- span_subtype == js（span_name == browser.error）

| 字段                                       | 类型      | 描述        | 备注                                                                   |
|------------------------------------------|---------|-----------|----------------------------------------------------------------------|
| `attributes.error.handled`               | boolean | 错误是否被捕获   |                                                                      |
| `attributes.error.source`                | str     | 错误来源      | 枚举值：<br/>- window.error（固定值）<br/>- resource<br/>- unhandledrejection |
| `attributes.error.window_count`          | int     | 窗口级错误累计次数 |                                                                      |
| `attributes.error.cross_origin`          | boolean | 跨域脚本错误    | 条件字段：仅跨域脚本错误（消息为 `"Script error."` 且无 stack / filename）时存在           |
| `attributes.code.column`                 | int     | 代码列号      |                                                                      |
| `attributes.code.filepath`               | str     | 代码文件路径    |                                                                      |
| `attributes.code.lineno`                 | int     | 代码行号      |                                                                      |
| `attributes.exception.fingerprint`       | str     | 异常指纹      | 用于聚合同类异常                                                             |
| `attributes.exception.message`           | str     | 异常完整消息    |                                                                      |
| `attributes.exception.message_short`     | str     | 异常简短消息    | 适合列表展示                                                               |
| `attributes.exception.stacktrace`        | str     | 异常堆栈信息    |                                                                      |
| `attributes.exception.stack_top_frame`   | str     | 堆栈顶部帧     |                                                                      |
| `attributes.exception.type`              | str     | 异常类型      |                                                                      |
| `events.name`                            | str     | 事件名称      |                                                                      |
| `events.timestamp`                       | str     | 事件发生时间戳   |                                                                      |
| `events.attributes.message`              | str     | 事件消息      |                                                                      |
| `events.attributes.exception.type`       | str     | 异常类型      |                                                                      |
| `events.attributes.exception.message`    | str     | 异常的简短消息   |                                                                      |
| `events.attributes.exception.stacktrace` | str     | 异常的堆栈信息   | 根据 error 实例提取，不一定存在                                                  |

- span_subtype == promise（span_name == browser.unhandledrejection）

| 字段                                       | 类型      | 描述        | 备注                                                                   |
|------------------------------------------|---------|-----------|----------------------------------------------------------------------|
| `attributes.error.handled`               | boolean | 错误是否被捕获   |                                                                      |
| `attributes.error.source`                | str     | 错误来源      | 枚举值：<br/>- window.error（固定值）<br/>- resource<br/>- unhandledrejection |
| `attributes.error.window_count`          | int     | 窗口级错误累计次数 |                                                                      |
| `attributes.exception.fingerprint`       | str     | 异常指纹      | 用于聚合同类异常                                                             |
| `attributes.exception.message`           | str     | 异常完整消息    |                                                                      |
| `attributes.exception.message_short`     | str     | 异常简短消息    | 适合列表展示                                                               |
| `attributes.exception.stacktrace`        | str     | 异常堆栈信息    |                                                                      |
| `attributes.exception.stack_top_frame`   | str     | 堆栈顶部帧     |                                                                      |
| `attributes.exception.type`              | str     | 异常类型      |                                                                      |
| `events.name`                            | str     | 事件名称      |                                                                      |
| `events.timestamp`                       | str     | 事件发生时间戳   |                                                                      |
| `events.attributes.message`              | str     | 事件消息      |                                                                      |
| `events.attributes.exception.type`       | str     | 异常类型      |                                                                      |
| `events.attributes.exception.message`    | str     | 异常的简短消息   |                                                                      |
| `events.attributes.exception.stacktrace` | str     | 异常的堆栈信息   | 根据 error 实例提取，不一定存在                                                  |

- span_subtype == resource_load（span_name == browser.resource_error）

| 字段                                       | 类型      | 描述            | 备注                                                                   |
|------------------------------------------|---------|---------------|----------------------------------------------------------------------|
| `attributes.error.handled`               | boolean | 错误是否被捕获       |                                                                      |
| `attributes.error.source`                | str     | 错误来源          | 枚举值：<br/>- window.error（固定值）<br/>- resource<br/>- unhandledrejection |
| `attributes.error.window_count`          | int     | 窗口级错误累计次数     |                                                                      |
| `attributes.exception.fingerprint`       | str     | 异常指纹          | 用于聚合同类异常                                                             |
| `attributes.exception.message`           | str     | 异常完整消息        |                                                                      |
| `attributes.exception.message_short`     | str     | 异常简短消息        | 适合列表展示                                                               |
| `attributes.exception.stacktrace`        | str     | 异常堆栈信息        |                                                                      |
| `attributes.exception.stack_top_frame`   | str     | 堆栈顶部帧         |                                                                      |
| `attributes.exception.type`              | str     | 异常类型          | `TypeError` / `Error` 等                                              |
| `attributes.html.tag`                    | str     | 关联 HTML 标签    | 资源类错误时出现，例如 `IMG`                                                    |
| `attributes.url.full`                    | str     | 失败资源 URL（已脱敏） |                                                                      |
| `events.name`                            | str     | 事件名称          |                                                                      |
| `events.timestamp`                       | str     | 事件发生时间戳       |                                                                      |
| `events.attributes.message`              | str     | 事件消息          |                                                                      |
| `events.attributes.exception.type`       | str     | 异常类型          |                                                                      |
| `events.attributes.exception.message`    | str     | 异常的简短消息       |                                                                      |
| `events.attributes.exception.stacktrace` | str     | 异常的堆栈信息       | 根据 error 实例提取，不一定存在                                                  |

- span_subtype == blank_screen（span_name == browser.blank_screen）

| 字段                                       | 类型      | 描述              | 备注 |
|------------------------------------------|---------|-----------------|----|
| `attributes.blank_screen.score`          | int  | 空白样本比例          |    |
| `attributes.blank_screen.threshold`      | int  | 判定阈值            |    |
| `attributes.blank_screen.detected`       | boolean | 是否判为白屏          |    |
| `attributes.blank_screen.root`           | str  | 采样根选择器          |    |
| `attributes.blank_screen.sample_total`   | int  | 采样点总数           |    |
| `attributes.blank_screen.sample_valid`   | int  | 有效采样数           |    |
| `attributes.blank_screen.sample_loading` | int  | loading 样本次数    |    |
| `attributes.blank_screen.center_element` | str  | 视口中心元素选择器       |    |
| `attributes.blank_screen.dom_node_count` | int  | body 下 DOM 节点总数 |    |

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
| `attributes.csp.window_count`        | int | 节流窗口内触发次数        |    |
| `attributes.csp.original_policy`     | str | 完整策略，仅窗口首条携带     |    |

### f. longtask（无数据上报，暂无法校验）

| 字段                                       | 类型     | 描述    | 备注 |
|------------------------------------------|--------|-------|----|
| `attributes.longtask.blocking_duration`  | int | 长任务时长 |    |
| `attributes.longtask.attribution_script` | str | 归因脚本  |    |

### g. action（无数据上报，暂无法校验）

| 字段                                 | 类型     | 描述                          | 备注  |
| ---------------------------------- | ------ | --------------------------- | --- |
| `attributes.action.type`           | str | 动作类型                        |     |
| `attributes.target_label`          | str | 跨类型主标签，用于统一检索               |     |
| `attributes.target.tag`            | str | 目标元素标签                      |     |
| `attributes.target.text_short`     | str | 目标文本前 32 字符                 |     |
| `attributes.session.start_time`    | int | 会话开始时间戳                     |     |
| `attributes.session.previous_id`   | str | 轮换前的 session.id             |     |
| `attributes.session.rotate.reason` | str | init/inactivity/maxLifetime |     |

### h. route

- span_name == browser.view

| 字段                           | 类型     | 描述      | 备注                                                                                                                                          |
|------------------------------|--------|---------|---------------------------------------------------------------------------------------------------------------------------------------------|
| `attributes.event.source`    | str | 路由事件来源  | 枚举值：<br/>- pushState<br/>- replaceState<br/>- popstate<br/>- hashchange                                                                     |
| `attributes.trace_scene`     | str | 追踪场景    | 枚举值：<br/>- route_change                                                                                                                     |
| `attributes.view.end_reason` | str | 结束原因    | 枚举值：<br/>- load（实际永不出现）<br/>- pushState<br/>- replaceState<br/>- popstate<br/>- hashchange<br/>- shutdown<br/>当该 view 被后续路由或 shutdown 结束时上报 |
| `attributes.url.previous`    | str | 上一页 URL | 来源页面地址                                                                                                                                      |

- span_name == browser.page_view

| 字段                               | 类型     | 描述          | 备注                                                                                                                                  |
|----------------------------------|--------|-------------|-------------------------------------------------------------------------------------------------------------------------------------|
| `attributes.event.source`        | str | 路由事件来源      | 枚举值：<br/>- pushState<br/>- replaceState<br/>- popstate<br/>- hashchange<br/>仅当 span_name 为 `browser.view` 和 `browser.page_view` 时上报 |
| `attributes.trace_scene`         | str | 追踪场景        | 枚举值：<br/>- route_change                                                                                                             |
| `attributes.url.previous`        | str | 上一页 URL     | 来源页面地址                                                                                                                              |

- span_name == browser.route_change（无数据，未验证）

| 字段                               | 类型     | 描述     | 备注                                                                                                                                  |
|----------------------------------|--------|--------|-------------------------------------------------------------------------------------------------------------------------------------|
| `attributes.event.source`        | str | 路由事件来源 | 枚举值：<br/>- pushState<br/>- replaceState<br/>- popstate<br/>- hashchange<br/>仅当 span_name 为 `browser.view` 和 `browser.page_view` 时上报 |
| `attributes.route.change.source` | str |        | routeTiming 插件                                                                                                                      |

### i. custom（无数据上报，暂无法校验）

- websocket 插件

| 字段                                        | 类型     | 描述                    | 备注          |
|-------------------------------------------|--------|-----------------------|-------------|
| `attributes.url.scheme`                   | str | `ws` / `wss`          |             |
| `attributes.server.address`               | str | 目标 host               |             |
| `attributes.network.protocol.name`        | str | 固定 `websocket`        |             |
| `attributes.websocket.direction`          | str | 消息收发方向 `in` / `out`   | metric 插件适用 |
| `attributes.websocket.error.phase`        | str | `connect` / `runtime` | 错误场景        |
| `attributes.websocket.error.window_count` | int | 错误日志节流窗口内触发次数         |             |
| `attributes.websocket.close.code`         | Mixed  | 关闭事件状态码               |             |
| `attributes.websocket.close.reason`       | Mixed  | 关闭原因                  |             |
| `attributes.websocket.close.was_clean`    | Mixed  | 是否为干净关闭               |             |
