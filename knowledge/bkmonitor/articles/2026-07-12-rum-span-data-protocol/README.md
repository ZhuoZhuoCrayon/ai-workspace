---
title: RUM 数据协议
tags: [rum, span, metric, log, data-protocol, opentelemetry, web]
description: 归档 bkmonitor RUM Web 的 Resource、Span、Metric 和 Log 协议，供数据上报、字段消费和协议核对使用。
created: 2026-07-12
updated: 2026-08-30
---
本文记录 `@blueking/open-telemetry` 当前上报的 Resource、Span、Metric 和 Log 字段。

| 状态                                                             | 描述             |
| -------------------------------------------------------------- | -------------- |
| ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | 已上报，保持现状。      |
| ![Deprecated](https://img.shields.io/badge/-deprecated-red)    | 已上报，但需要废弃。     |
| ![Development](https://img.shields.io/badge/-development-blue) | 新补充或字段位置变更。    |
| ![Backend](https://img.shields.io/badge/-backend-orange)       | 由后端生成，前端不直接上报。 |

原则：
* Aegis、DataDog 后续统一转成 Otel Span 协议，同领域字段尽量对齐前两个 SDK，需控制字段数量，避免出现需转换 150+ 字段的情况。
* 控制字段规模：输出可覆盖 Otel & Aegis & DataDog SDK 最简协议，其他不必要字段统一省略，减少初始技术负债（字段一旦放出但没有真正使用，稳定后一旦有需求变更，就有兼容风险）。
* 指标：Web Vitals 指标由接收端派生，SDK 无需埋点。

## 0x01 用户真实监控模型

```text
Session
└── View
    ├── Vital：FCP / LCP / CLS / INP / TTFB
    ├── Action
    ├── Resource
    ├── Error
    └── Long Task
```

## 0x02 公共字段

### a. 顶层字段

| 字段               | 状态                                                             | 类型      | 描述                                                                             | 备注                                                                          |
| ---------------- | -------------------------------------------------------------- | ------- | ------------------------------------------------------------------------------ | --------------------------------------------------------------------------- |
| `time`           | ![Backend](https://img.shields.io/badge/-backend-orange)       | str     | 数据上报时间（毫秒时间戳字符串）                                                               | --                                                                          |
| `app_name`       | ![Backend](https://img.shields.io/badge/-backend-orange)       | str     | 应用名称                                                                           | --                                                                          |
| `bk_biz_id`      | ![Backend](https://img.shields.io/badge/-backend-orange)       | str     | 业务 ID                                                                          | --                                                                          |
| `trace_id`       | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str     | Trace ID                                                                       | --                                                                          |
| `trace_state`    | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str     | Trace 状态                                                                       | --                                                                          |
| `span_name`      | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str     | Span 名称                                                                        | --                                                                          |
| `span_id`        | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str     | Span ID                                                                        | --                                                                          |
| `parent_span_id` | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str     | 父 Span ID                                                                      | --                                                                          |
| `status`         | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | Status  | Span 执行状态                                                                      | 包含 `code` 和 `message`。                                                      |
| `kind`           | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | enum    | [Span 类型](https://opentelemetry.io/zh/docs/concepts/signals/traces/#span-kind) | 枚举值：<br>- 未定义：0<br>- 内部调用：1<br>- 同步被调：2<br>- 同步主调：3<br>- 异步主调：4<br>- 异步被调：5 |
| `resource`       | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | object  | 资源信息                                                                           | 服务、环境、SDK 等描述信息。                                                            |
| `events`         | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | Event[] | 事件列表                                                                           | 异常详情和 Long Task 脚本明细通过 Span Event 承载。                                       |
| `links`          | ![Development](https://img.shields.io/badge/-development-blue) | Link[]  | [Span 链接](https://opentelemetry.io/docs/concepts/signals/traces/#span-links)   | 链接的存在是为了 Span 同其他 Span 建立关联，从而表明存在因果关系。                                     |
| `attributes`     | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | object  | 属性                                                                             | 浏览器、设备、网络、异常等各类语义标签和度量。                                                     |
| `start_time`     | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | int     | 开始时间（微秒）                                                                       | --                                                                          |
| `end_time`       | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | int     | 结束时间（微秒）                                                                       | --                                                                          |
| `elapsed_time`   | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | int     | 耗时（微秒）                                                                         | --                                                                          |

### b. Resource

| 字段                                                                                                                     | 状态                                                             | 类型     | 描述          | 备注                                             |
| ---------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- | ------ | ----------- | ---------------------------------------------- |
| `resource.service.name`                                                                                                | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | 服务名         | --                                             |
| `resource.service.version`                                                                                             | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | 版本          | --                                             |
| [`resource.deployment.environment.name`](https://opentelemetry.io/docs/specs/semconv/resource/deployment-environment/) | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | 环境          | 如 `development`、`production`、`staging`、`test`。 |
| `resource.session.sample_rate`                                                                                         | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | number | Session 采样率 | 取值范围为 `0`～`1`。                                 |
| `resource.telemetry.sdk.version`                                                                                       | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | SDK 版本      | --                                             |
| [`resource.telemetry.sdk.language`](https://opentelemetry.io/docs/specs/semconv/resource/#telemetry-sdk)               | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | enum   | 语言          | `webjs`。                                       |
| `resource.telemetry.sdk.name` *[1]*                                                                                    | ![Development](https://img.shields.io/badge/-development-blue) | str    | SDK 名称      | --                                             |
| `resource.device.type`                                                                                                 | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | enum   | 设备类型        | `desktop`、`mobile`、`tablet`、`other`。           |
| `resource.user_agent.name`                                                                                             | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | 代理名称        | 通常指的是浏览器的名称，如 `Chrome`、`Edge`。                 |
| `resource.user_agent.version`                                                                                          | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | 代理版本        | 通常指的是浏览器的名称，如 `149`、`151`。                     |
| `resource.user_agent.os.name`                                                                                          | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | 操作系统名       | 如 `macOS`、`Windows`、`Android`。                 |

**[1] `resource.telemetry.sdk.name`**：`blueking`（蓝鲸 Otel SDK，当前值为 @blueking/open-telemetry，需修改。）｜aegis（Aegis SDK）。

### c. Status

| 字段               | 状态                                                         | 类型  | 描述   | 备注                           |
| ---------------- | ---------------------------------------------------------- | --- | ---- | ---------------------------- |
| `status.code`    | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 状态码  | 0（未设置）<br />1（正常）<br />2（异常） |
| `status.message` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 状态描述 | 如 `Failed to fetch`          |

### d. Event

| 字段                                                                      | 状态                                                         | 类型     | 描述            | 备注                   |
| ----------------------------------------------------------------------- | ---------------------------------------------------------- | ------ | ------------- | -------------------- |
| `events[].name` *[1]*                                                   | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str    | 事件名           |                      |
| `events[].timestamp`                                                    | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int    | 事件发生时间（微秒）    |                      |
| `events[].attributes.exception.type`                                    | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str    | 异常类型          | 如 `TypeError`。       |
| `events[].attributes.exception.message`                                 | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str    | 异常消息          | 如 `Failed to fetch`。 |
| `events[].attributes.exception.stacktrace`                              | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str    | 异常堆栈          |                      |
| `events[].attributes.long_task.script.duration`                         | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 脚本耗时（ms）      |                      |
| `events[].attributes.long_task.script.execution_start`                  | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 脚本执行开始时间（ms）  |                      |
| `events[].attributes.long_task.script.forced_style_and_layout_duration` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 强制样式与布局耗时（ms） |                      |
| `events[].attributes.long_task.script.pause_duration`                   | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 暂停耗时（ms）      |                      |
| `events[].attributes.long_task.script.source_char_position`             | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 源码字符位置        |                      |
| `events[].attributes.long_task.script.start_time`                       | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 脚本开始时间（ms）    |                      |
| `events[].attributes.long_task.script.invoker`                          | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str    | 调用方           |                      |
| `events[].attributes.long_task.script.invoker_type`                     | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str    | 调用方类型         |                      |
| `events[].attributes.long_task.script.source_function_name`             | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str    | 源函数名          |                      |
| `events[].attributes.long_task.script.source_url`                       | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str    | 已脱敏的脚本 URL    |                      |
| `events[].attributes.long_task.script.window_attribution`               | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str    | Window 归因     |                      |

**[1] `events[].name`**：「异常」需将事件名固定为 `exception`。

---

### f. Link

| 字段                 | 状态                                                             | 类型  | 描述         | 备注  |
| ------------------ | -------------------------------------------------------------- | --- | ---------- | --- |
| `links[].trace_id` | ![Development](https://img.shields.io/badge/-development-blue) | str | 关联 TraceID |     |
| `links[].span_id`  | ![Development](https://img.shields.io/badge/-development-blue) | str | 关联 SpanID  |     |

**[1] `links[].trace_id`**：满足 `attributesspan_type=resource, attributes.resource.type=xhr or fetch` 时，需将前端生成的 TraceID 记录到该字段。


## 0x03 Attributes

### a. 基础字段

| 字段                           | 状态                                                         | 类型   | 描述      | 备注                                             |
| ---------------------------- | ---------------------------------------------------------- | ---- | ------- | ---------------------------------------------- |
| `attributes.user.id`         | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str  | 用户 ID   | --                                             |
| `attributes.span_type` *[1]* | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | enum | Span 类型 | --                                             |
| `attributes.outcome.type`    | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | enum | 执行结果    | `success`、`warning`、`error`、`timeout`、`abort`。 |


**[1] `attributes.span_type`**：

| 值           | 描述                   |
| ----------- | -------------------- |
| `session`   | Session 创建、轮换或结束。    |
| `view`      | 页面首次加载或路由视图生命周期。     |
| `resource`  | 静态资源、Fetch 或 XHR 请求。 |
| `error`     | 浏览器错误、白屏或 CSP 违规。    |
| `vital`     | Web Vitals 指标。       |
| `long_task` | Long Task 或长动画帧。     |
| `action`    | 用户交互或主动上报的 Action。   |
| `websocket` | WebSocket 生命周期事件。    |
| `custom`    | 主动上报的自定义事件。          |

### b. [error](https://opentelemetry.io/docs/specs/semconv/registry/attributes/error/)


| 字段                              | 状态                                                          | 类型      | 描述         | 备注                                                                   |
| ------------------------------- | ----------------------------------------------------------- | ------- | ---------- | -------------------------------------------------------------------- |
| `attributes.error.message`      | ![Stable](https://img.shields.io/badge/-stable-lightgreen)  | str     | 错误信息       | --                                                                   |
| `attributes.error.handled`      | ![Stable](https://img.shields.io/badge/-stable-lightgreen)  | boolean | 错误是否被捕获    | --                                                                   |
| `attributes.error.source`       | ![Stable](https://img.shields.io/badge/-stable-lightgreen)  | str     | 错误来源       | 枚举值：<br/>- window.error（固定值）<br/>- resource<br/>- unhandledrejection |
| `attributes.code.column`        | ![Stable](https://img.shields.io/badge/-stable-lightgreen)  | int     | 代码列号       |                                                                      |
| `attributes.code.filepath`      | ![Stable](https://img.shields.io/badge/-stable-lightgreen)  | str     | 代码文件路径     |                                                                      |
| `attributes.code.lineno`        | ![Stable](https://img.shields.io/badge/-stable-lightgreen)  | int     | 代码行号       |                                                                      |

### c. [browser](https://opentelemetry.io/docs/specs/semconv/registry/attributes/browser/)

| 字段                                   | 状态                                                         | 类型  | 描述      | 备注                           |
| ------------------------------------ | ---------------------------------------------------------- | --- | ------- | ---------------------------- |
| `attributes.browser.screen.height`   | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 屏幕尺寸的高度 | Aegis 使用 `sr = 1728 * 1117`。 |
| `attributes.browser.screen.width`    | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 屏幕尺寸的宽度 | --                           |
| `attributes.browser.viewport.height` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 视口尺寸的高度 | Aegis 使用 `vp = 576 * 918`。   |
| `attributes.browser.viewport.width`  | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 视口尺寸的宽度 | --                           |

### d. [device](https://opentelemetry.io/docs/specs/semconv/registry/attributes/device/)

| 字段                     | 状态                                                         | 类型  | 描述   | 备注                                        |
| ---------------------- | ---------------------------------------------------------- | --- | ---- | ----------------------------------------- |
| `attributes.device.id` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 设备标识 | 如 `fd136680-a37b-45ea-80ee-365bfdc7f82e`。 |

### e. [network](https://opentelemetry.io/docs/specs/semconv/registry/attributes/network/)

| 字段                                   | 状态                                                             | 类型   | 描述      | 备注                                                          |
| ------------------------------------ | -------------------------------------------------------------- | ---- | ------- | ----------------------------------------------------------- |
| `attributes.network.connection.type` | ![Development](https://img.shields.io/badge/-development-blue) | enum | 连接类型    | 直接使用浏览器 `navigator.connection.type` 的原始值；字段不存在时不上报。 |
| `attributes.network.effective_type`  | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str  | 有效网络质量  | --                                                          |
| `attributes.network.status`          | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | enum | 网络连接状态  | `connected`、`not_connected`。                                |
| `attributes.network.protocol.name`   | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | enum | 应用层网络协议 | 仅 WebSocket Span 上报，固定为 `websocket`；HTTP Resource Span 不上报。 |

**[1] `attributes.network.connection.type`**：表示设备当前使用的物理网络连接方式。SDK 直接上报
[`navigator.connection.type`](https://wicg.github.io/netinfo/#connectiontype-enum)；浏览器不支持该 API
或没有返回 `type` 时不携带该字段。该字段对应 DataDog 的 `connectivity.interfaces` 和 Aegis 的 `netType`。

Aegis 将「连接类型」「网络质量」整合成 `netType`（`wifi`、`wired`、`2G`、`3G`、`5G`、`6G`），不推荐这种做法。
转换 Aegis 数据时，`wifi` 保持不变，`wired` 映射为 `ethernet`，移动网络代际映射为 `cellular`。

| 值          | 描述       | 备注                                      |
| ---------- | -------- | --------------------------------------- |
| `bluetooth` | 蓝牙网络     | 通过蓝牙网络连接。                               |
| `cellular`  | 蜂窝移动网络   | 不表示具体移动网络代际。                            |
| `ethernet`  | 以太网      | Aegis 的 `wired` 映射为该值。                   |
| `mixed`     | 混合连接     | 浏览器同时使用多种连接方式。                          |
| `none`      | 无网络连接    | 通常与 `network.status=not_connected` 同时出现。 |
| `other`     | 其他连接方式   | 浏览器知道连接类型，但不属于已列出的类型。                   |
| `unknown`   | 未知连接方式   | 已建立网络连接，但浏览器无法或不愿提供连接类型。                |
| `wifi`      | Wi-Fi 网络 | 仅表示通过 Wi-Fi 连接，不代表网络一定快。                 |
| `wimax`     | WiMAX 网络 | 通过 WiMAX 连接。                             |

**[2] `attributes.network.effective_type`**：表示浏览器根据延迟和下载速度估算出的实际网络质量，等同与 DataDog（`connectivity.effective_type`）、Aegis（`netType`）。

| 值         | 描述   | 备注                         |
| --------- | ---- | -------------------------- |
| `slow-2g` | 极慢网络 | 页面和图片加载非常慢，通常只能满足少量文本传输。   |
| `2g`      | 较慢网络 | 简单页面可以打开，图片、脚本和接口请求可能明显缓慢。 |
| `3g`      | 中等网络 | 普通网页基本可用，但大资源和复杂页面仍可能等待。   |
| `4g`      | 较快网络 | 延迟和带宽表现较好，适合大多数 Web 应用。    |

### f. session

| 字段                                    | 状态                                                          | 类型      | 描述       | 备注                                              |
| ------------------------------------- | ----------------------------------------------------------- | ------- | -------- | ----------------------------------------------- |
| `attributes.session.has_replay`       | ![Stable](https://img.shields.io/badge/-stable-lightgreen)  | boolean | 是否回放     | --                                              |
| `attributes.session.id`               | ![Stable](https://img.shields.io/badge/-stable-lightgreen)  | str     | 会话 ID    | --                                              |
| `attributes.session.type`             | ![Stable](https://img.shields.io/badge/-stable-lightgreen)  | enum    | 会话类型     | 当前固定为 `user`。                                   |
| `attributes.session.phase` *[1]*      | ![Stable](https://img.shields.io/badge/-stable-lightgreen)  | enum    | 会话生命周期阶段 | --                                              |

**[1] `attributes.session.phase`**：

| 值       | 描述                     |
| ------- | ---------------------- |
| `start` | 创建首个 Session。          |
| `rotate` | 旧 Session 到期后创建新 Session。 |
| `end`   | 当前 Session 结束。          |

### g. view

| 字段                                    | 状态                                                             | 类型     | 描述                      | 备注                                            |
| ------------------------------------- | -------------------------------------------------------------- | ------ | ----------------------- | --------------------------------------------- |
| `attributes.view.id`                  | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | 视图 ID                   |                                               |
| `attributes.view.name` *[1]*          | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | 视图名称                    | 如 `/apm/home`。                                |
| `attributes.view.loading_type` *[2]*  | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | 视图加载类型                  | --                                            |
| `attributes.view.url`                 | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | 视图 URL                  | 如 `https://example.com/cur`。                  |
| `attributes.view.previous`            | ![Development](https://img.shields.io/badge/-development-blue) | str    | 视图 URL（前一个）             | 如 `https://example.com/pre`。                  |
| `attributes.view.previous_url_template` | ![Development](https://img.shields.io/badge/-development-blue) | str  | 前序视图路径模板                | 与 `view.url_template` 使用同一规则；初始 View 为空字符串。 |
| `attributes.view.referrer`            | ![Development](https://img.shields.io/badge/-development-blue) | str    | 初始来源页面 URL              | 仅首次加载且值非空时上报，需进行 URL 脱敏。                      |
| `attributes.view.url_template` *[3]*  | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | 视图路径分组                  | 如 `/apm/home`。                                |
| `attributes.view.loading_time`        | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | number | 视图加载耗时（ms）              | 加载时间计算完成后上报。                                  |
| `attributes.view.loading_time_source` | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | enum   | 视图加载耗时来源                | `auto`、`manual`。                              |
| `attributes.view.first_byte`          | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | number | 首字节时间（ms）               | 仅初始导航存在。                                      |
| `attributes.view.dom_interactive`     | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | number | DOM 可交互时间（ms）           | 仅初始导航存在。                                      |
| `attributes.view.dom_content_loaded`  | ![Stable\|43](https://img.shields.io/badge/-stable-lightgreen) | number | DOMContentLoaded 时间（ms） | 仅初始导航存在。                                      |
| `attributes.view.dom_complete`        | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | number | DOM Complete 时间（ms）     | 仅初始导航存在。                                      |
| `attributes.view.load_event`          | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | number | Load Event 时间（ms）       | 仅初始导航存在。                                      |
| `attributes.view.phase` *[4]*         | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | enum   | 视图生命周期阶段                | 枚举值：<br>- start<br>- update<br>- end          |
| `attributes.view.started_at`          | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | number | 视图开始时间（ms）              | 取 `performance.timeOrigin`。                   |
| `attributes.view.version`             | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | int    | 视图事件版本号                 | 同一 `attributes.view.id` 从 `1` 开始递增，用于排序和幂等合并。 |
| `attributes.view.end_reason`          | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | 结束原因                    | --                                            |

**[1] `attributes.view.name`**：仅由 `startView({ name })` 或 `setViewName` 显式设置；未设置时，展示层可回退到 `view.url_template`。

**[2] `attributes.view.loading_type`**：

| 值                 | 描述              |
| ----------------- | --------------- |
| `initial_load`    | 首次页面加载（初始导航）    |
| `route_change`    | SPA 路由切换        |
| `session_renewal` | 会话续期后重建         |
| `bf_cache`        | 从浏览器 BFCache 恢复 |

**[3] `attributes.view.url_template`**：用于聚合的页面路径。默认把数字 ID、UUID 和长十六进制段替换为 `:id`，也可由 `tracking.view.getUrlTemplate` 自定义。

**[4] `attributes.view.phase`**：当前 View Span 的生命周期阶段，Schema v3 不再用一条长 Span 表达整个 View，而是发送多条瞬时生命周期 Span。


```text
逻辑 View：view.id=view-A
│
├── Span #1：version=1，phase=start
│   │
│   ├── 上报时机：View 创建
│   ├── view.loading_time       = 不存在
│   ├── view.first_byte         = 120     ← 创建时已可读取
│   ├── view.dom_interactive    = 不存在   ← 此时还是 0
│   ├── view.dom_content_loaded = 不存在
│   ├── view.dom_complete       = 不存在
│   └── view.load_event         = 不存在
│
│   SDK 创建 View 时读取一次 PerformanceNavigationTiming。
│   只写入当时已经大于 0 的字段。
│
├── Span #2：version=2，phase=update
│   │
│   ├── 上报时机：Loading Time 计算完成
│   ├── view.loading_time       = 820
│   ├── view.first_byte         = 120
│   ├── view.dom_interactive    = 350
│   ├── view.dom_content_loaded = 420
│   ├── view.dom_complete       = 680
│   └── view.load_event         = 700
│
│   SDK 等待以下两个条件完成：
│   ├── loadEventEnd 已产生
│   └── 页面请求、资源和 DOM 活动结束
│
│   然后重新读取 PerformanceNavigationTiming，
│   将六个字段一起放入 update Span。
│
└── Span #3：version=3，phase=end
    │
    ├── 上报时机：路由切换或页面离开
    ├── view.loading_time       = 820
    ├── view.first_byte         = 120
    ├── view.dom_interactive    = 350
    ├── view.dom_content_loaded = 420
    ├── view.dom_complete       = 680
    └── view.load_event         = 700

    end Span 不会重新计算这些字段，
    只是携带 View 当前的最终属性快照。
```


```text
时间 ───────────────────────────────────────────────────────────>

View A  ███████████████████████████████│
        ├─ 查询订单 Action
        └──── GET /api/orders ─────────┘
                                       │ 路由切换
View B                                 ███████████████████████│
                                       ├─ 查询用户 Action
                                       └── GET /api/users ────┘
```

### h. resource

| 字段                                           | 状态                                                         | 类型      | 描述                  | 备注                                                                      |
| -------------------------------------------- | ---------------------------------------------------------- | ------- | ------------------- | ----------------------------------------------------------------------- |
| `attributes.resource.type`                   | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | enum    | 资源类型                | --                                                                      |
| `attributes.resource.size`                   | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int     | 资源大小                | --                                                                      |
| `attributes.resource.transfer_size`          | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int     | 传输大小                | --                                                                      |
| `attributes.resource.decoded_body_size`      | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int     | 解码后正文大小             | --                                                                      |
| `attributes.resource.encoded_body_size`      | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int     | 编码后正文大小             | --                                                                      |
| `attributes.resource.protocol`               | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | 传输协议                | 浏览器提供下一跳协议时存在，如 `h2`、`h3`、`http/1.1`。                                   |
| `attributes.resource.cache.hit` *[3]*        | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | boolean | 缓存命中标记              | 命中时为 `true`，未命中或无法判断时不写入。                                               |
| `attributes.resource.delivery_type` *[4]*          | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | 交付类型                | 浏览器返回非空值时存在。                                                         |
| `attributes.resource.render_blocking_status` *[5]* | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | enum    | 渲染阻塞状态              | 浏览器支持该字段时存在。                                                         |
| `attributes.resource.redirect.start`         | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 重定向开始时间             | --                                                                      |
| `attributes.resource.redirect.duration`      | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 重定向耗时               | --                                                                      |
| `attributes.resource.worker.start`           | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | Service Worker 开始时间 | --                                                                      |
| `attributes.resource.worker.duration`        | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | Service Worker 耗时   | --                                                                      |
| `attributes.resource.dns.start`              | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | DNS 查询开始时间          | --                                                                      |
| `attributes.resource.dns.duration`           | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | DNS 查询耗时            | --                                                                      |
| `attributes.resource.connect.start`          | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 传输连接开始时间            | --                                                                      |
| `attributes.resource.connect.duration`       | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 传输连接耗时              | --                                                                      |
| `attributes.resource.ssl.start`              | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | TLS 握手开始时间          | --                                                                      |
| `attributes.resource.ssl.duration`           | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | TLS 握手耗时            | --                                                                      |
| `attributes.resource.first_byte.start`       | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 首字节阶段开始时间           | --                                                                      |
| `attributes.resource.first_byte.duration`    | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 首字节耗时               | --                                                                      |
| `attributes.resource.download.start`         | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 下载开始时间              | --                                                                      |
| `attributes.resource.download.duration`      | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 下载耗时                | --                                                                      |

**[1] `attributes.resource.type`**：

| 值                  | 描述                                           |
| ------------------ | -------------------------------------------- |
| `fetch`            | Fetch API 请求。                                |
| `xhr`              | XMLHttpRequest 请求。                           |
| `script`           | `<script>`、模块或 Worker 加载的脚本资源。               |
| `link`             | `<link>` 加载的资源，如样式表、预加载和预取资源。                |
| `img` / `image`    | HTML 或 SVG 图片元素加载的资源。                        |
| `css`              | CSS `url()`、`@import` 等规则加载的资源，不表示 CSS 文件本身。 |
| `iframe` / `frame` | 内嵌页面加载的文档资源。                                 |
| `other`            | 浏览器未识别发起方式、`initiatorType` 为空或未单列的其他类型。      |
| ...                | ..                                           |

**[2] 单位**：`xx_size` 为 bytes，`duration` & `start` 为毫秒。

**[3] `attributes.resource.cache.hit`**

满足任一条件时，SDK 写入 `true`：

| 条件 | 结果 |
| --- | --- |
| `deliveryType=cache` | `true` |
| `transferSize=0 && decodedBodySize>0` | `true` |
| 其他 | 不写入，不写 `false` |

ETag（实体标签）是服务器提供的资源版本标识。浏览器按以下流程校验缓存：

```text
缓存 ETag → If-None-Match → 304 → 复用本地正文
```

`deliveryType=cache` 与 `transferSize>0` 不冲突。[Resource Timing](https://www.w3.org/TR/resource-timing/) 把 `validated` 缓存的 `transferSize` 记为 `300`，不是正文大小。

**[4] `attributes.resource.delivery_type`**：

| 常见值                     | 描述                                                         |
| ----------------------- | ---------------------------------------------------------- |
| `cache`                 | 由浏览器 HTTP 缓存交付，包括本地缓存和网络校验缓存。                              |
| `navigational-prefetch` | 由导航预取缓冲区交付。                                                |
| `cache-storage`         | 由 Cache Storage 交付，包括 Service Worker Fetch Handler 和静态路由命中。 |

规范来源：[Resource Timing](https://www.w3.org/TR/resource-timing/)、[Prefetch](https://wicg.github.io/nav-speculation/prefetch.html)、[Chromium Cache Storage Timing](https://chromium.googlesource.com/chromium/src/+/lkgr/docs/experiments/service-worker-static-routing-api-timing-info.md)。

SDK 原样上报浏览器返回的非空值，空值不写入。

**[5] `attributes.resource.render_blocking_status`**：

| 值              | 描述          |
| -------------- | ----------- |
| `blocking`     | 资源可能阻塞页面渲染。 |
| `non-blocking` | 资源不会阻塞页面渲染。 |

取值定义见 [Resource Timing](https://www.w3.org/TR/resource-timing/)。浏览器不支持该字段时，SDK 不写入。

### i. action

| 字段                                         | 状态                                                         | 类型    | 描述     |
| ------------------------------------------ | ---------------------------------------------------------- | ----- | ------ |
| `attributes.action.id`                     | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str   | --     |
| `attributes.action.type` *[2]*             | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str   | 动作类型   |
| `attributes.action.target.name`            | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str   | 目标元素名称 |
| `attributes.action.target.tag`             | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str   | 目标元素标签 |
| `attributes.action.frustration.type` *[3]* | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str[] | 挫败类型   |


**[1] `attributes.action.loading_time`**：`loading_time` 可直接使用外层 `elapsed_time`。

**[2] `attributes.action.type`**：

| 常见值                  | 描述                                 |
| -------------------- | ---------------------------------- |
| `click`              | 鼠标或指针设备触发的点击，蓝鲸 Web 自动 Action 当前使用该值。 |
| `custom`             | 通过 SDK API 主动上报的自定义 Action。          |
| `tap`                | 触屏设备上的单次轻触。                        |
| `scroll`             | 页面或滚动容器的滚动操作。                      |
| `swipe`              | 触屏设备上的滑动手势。                        |
| `application_start`  | 应用启动，常用于移动端或桌面端。                  |
| `back`               | 返回上一页面或上一导航状态，常用于移动端。             |

以上是跨端常见值，不是封闭枚举。蓝鲸 Web 当前产生 `click` 和 `custom`。转换 Aegis 数据时，还可能保留接入方配置的 DOM 事件名。

**[3] `attributes.action.frustration.type`**：

| 值             | 描述                                                                                   |
| ------------- | ------------------------------------------------------------------------------------ |
| `rage_click`  | [a] `1 s` 内对同一 DOM 元素连续点击至少 `3` 次，且相邻点击距离不超过 `100 px`。<br />[b] 滚动或文本选择会中断或撤销判定。     |
| `dead_click`  | [a] 点击后未检测到请求、资源加载、长任务、DOM 变化、打开窗口或错误，也没有输入、滚动或文本选择。<br />[b] 链接、文本输入框等难以可靠判断的目标会排除。 |
| `error_click` | Action 生命周期内检测到前端错误。                                                                 |

该字段为数组，同一个 Action 可以同时命中多个值；未命中时不写入。消费端应按集合处理，不依赖数组顺序。这些信号是 SDK 的启发式判断，不等同于业务操作失败。

### j. http & [url](https://opentelemetry.io/docs/specs/semconv/registry/attributes/url/) & server

| 字段                                     | 状态                                                         | 类型  | 描述     |                              |
| -------------------------------------- | ---------------------------------------------------------- | --- | ------ | ---------------------------- |
| `attributes.url.full`                  | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 完整 URL | 如 `https://example.com/apm`。 |
| `attributes.url.scheme`                | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 协议     | 如 `ws`、`wss`。                |
| `attributes.url.template`              | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 请求路径   | 如 `/api/users/`。             |
| `attributes.http.request.method`       | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 请求方法   | 如 `GET`、`POST`。              |
| `attributes.http.response.status_code` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 返回码    | 如 `200`、`404`。               |
| `attributes.server.address`            | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 地址     | 如 `example.com`。             |
| `attributes.server.port`               | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 端口     | --                           |

### k. vital

| 字段                                            | 状态                                                         | 类型     | 描述                   | 备注                                   |
| --------------------------------------------- | ---------------------------------------------------------- | ------ | -------------------- | ------------------------------------ |
| `attributes.vital.id`                         | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str    | Vital 唯一标识           |                                      |
| `attributes.vital.metric`                     | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | enum   | 指标名                  |                                      |
| `attributes.vital.value`                      | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 指标测量值                |                                      |
| `attributes.vital.inp.input_delay`            | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 输入延迟（ms）             | 用户发起交互（如点击）到事件处理器开始执行的等待时间，反映主线程繁忙程度 |
| `attributes.vital.inp.interaction_target`     | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str    | 交互目标元素标识             | 如 `div`。                             |
| `attributes.vital.inp.interaction_type`       | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str    | 交互类型                 | --                                   |
| `attributes.vital.inp.processing_duration`    | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 处理耗时（ms）             | --                                   |
| `attributes.vital.inp.presentation_delay`     | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 呈现延迟（ms）             | --                                   |
| `attributes.vital.lcp.target`                 | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str    | DOM 选择器              | 如 `div`。                             |
| `attributes.vital.lcp.url`                    | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str    | 元素对应资源 URL（已脱敏）      | --                                   |
| `attributes.vital.lcp.resource_load_duration` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 资源加载耗时（ms）           | --                                   |
| `attributes.vital.lcp.element_render_delay`   | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 元素渲染延迟（ms）           | --                                   |
| `attributes.vital.ttfb.waiting_duration`      | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 请求就绪后的等待耗时（ms）       | --                                   |
| `attributes.vital.ttfb.dns_duration`          | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | DNS 解析耗时（ms）         | --                                   |
| `attributes.vital.ttfb.connection_duration`   | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | TCP + TLS 连接建立耗时（ms） | --                                   |
| `attributes.vital.ttfb.request_duration`      | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 请求发送后等待首字节耗时（ms）     | --                                   |

**[1] `attributes.vital.metric`**：

| 值    | 描述                                                                    | 备注                                                                                                |
| ---- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| cls  | [累积布局偏移（Cumulative Layout Shift）](https://web.dev/articles/cls)       | 在整个页面生命周期中，每次出现的意外布局变化所导致的最大布局变化得分的累积值，为了提供良好的用户体验，网站的 CLS 得分应控制在 0.1 或更低。                        |
| inp  | [交互到下一次绘制（Interaction to Next Paint）](https://web.dev/articles/inp)   | 记录用户与页面进行的所有交互的延迟情况，并给出一个综合评分（通常是 P98，忽略极端值），较低的 INP 值意味着页面能够快速响应所有或绝大多数用户交互，INP 值在用户离开页面时会被计算出来。 |
| lcp  | [最大内容绘制（Largest Contentful Paint, LCP）](https://web.dev/articles/lcp) | Core Web Vital 中的一个重要且稳定的指标，测量从页面开始加载，到视窗中可见的最大图像、文本块或视频的渲染时间，用于衡量页面加载的速度（用户感受：页面主要内容出来了）。        |
| fcp  | [首次内容绘制（First Contentful Paint）](https://web.dev/articles/fcp)        | 从用户首次访问页面，到页面第一次显示出任何内容的耗时（用户感受：不是白屏了）。                                                           |
| ttfb | [首字节时间（Time to First Byte）](https://web.dev/articles/ttfb)            | 从用户开始导航到页面到响应首字节开始传输之间所经历的时间。                                                                     |

**[2] `attributes.vital.value`**：CLS 单位为 `1`，FCP、INP、LCP、TTFB 单位为 `ms`。

**[3] `attributes.vital.cls.largest_shift_value` & `attributes.vital.cls.largest_shift_target`**：Aegis & DataDog 无采集，废弃。

**[4] `attributes.vital.inp.interaction_type`**：交互类型。

| 值             | 描述            |
| ------------- | ------------- |
| `keyup`       | 松开按键          |
| `keydown`     | 按下按键          |
| `pointerdown` | 点击（鼠标、触屏、触控笔） |
| `pointerup`   | 松开            |

**[5] `attributes.vital.inp.processing_duration`**：事件处理回调（如 click handler）本身的执行时间，JS 逻辑过重时这个值会变大。

**[6] `attributes.vital.inp.presentation_delay`**：回调操作完成之后到该帧最终显示在用户屏幕上所需的时间。

**[7] `attributes.vital.lcp.element_render_delay`**：LCP 元素资源加载完成后，到浏览器真正渲染该元素之间的等待时间（主要由主线程阻塞（长任务/JS 执行）导致）。

**[8] `attributes.vital.lcp.resource_load_duration`**：LCP 元素依赖的外部资源（图片/字体等）从请求到下载完成的时间（如果 LCP 是纯文本节点，此项可能缺失），用于排查 CDN/网络/资源体积问题。

**[9] `attributes.vital.lcp.time_to_first_byte`**：从导航开始到收到首字节的耗时（LCP ≈ `time_to_first_byte` + `resource_load_duration` + `element_render_delay`）。

**[10] `attributes.vital.ttfb.waiting_duration`**：页面激活到浏览器开始 Fetch，或开始启动 Service Worker 前的时间（包含重定向及浏览器前置处理）。

**[11]  `attributes.vital.ttfb.dns_duration`**：解析慢通常由 DNS 服务器延迟、复杂 CNAME 链或本地 DNS 缓存失效导致（多国/多地域部署时此值可能偏高）。

**[12]  `attributes.vital.ttfb.dns_duration`**：TCP / QUIC 建连及 TLS 协商，连接复用时通常为 `0`。

**[12]  `attributes.vital.ttfb.request_duration`**：建连结束到收到首字节，包含调度空档、请求发送、网络 RTT 和服务端处理。


### l. blank_screen
> _**白屏（Blank Screen）**：非 Web 标准指标。页面可见且活动稳定后，SDK 对指定根元素范围内的视口进行采样；排除加载态样本后，如果空白样本占有效样本的比例达到阈值，并在二次检测中仍然成立，则判定为白屏。_

| 字段                                             | 状态                                                              | 类型      | 描述               | 备注                 |
| ---------------------------------------------- | --------------------------------------------------------------- | ------- | ---------------- | ------------------ |
| `attributes.blank_screen.reason` *[1]*         | ![Stable](https://img.shields.io/badge/-stable-lightgreen)      | str     | 白屏判定原因           |                    |
| `attributes.blank_screen.empty_ratio`          | ![Stable](https://img.shields.io/badge/-stable-lightgreen)      | number  | 有效样本中的空白比例       |                    |
| `attributes.blank_screen.empty_sample_count`   | ![Stable](https://img.shields.io/badge/-stable-lightgreen)      | int     | 空白采样数            |                    |

**[1] `attributes.blank_screen.reason`**：

| 值                | 描述                                                                                      |
| ---------------- | --------------------------------------------------------------------------------------- |
| `empty_viewport` | 配置的采样根元素存在，有效采样点的空白比例达到白屏阈值。                                                        |
| `missing_root`   | 未找到 `root_selector` 指定的根元素，SDK 回退到 `body`（不可用时使用 `documentElement`）检测，且回退检测仍达到白屏阈值。 |

### m. longtask

| 字段                                              | 状态                                                              | 类型     | 描述                   |
| ----------------------------------------------- | --------------------------------------------------------------- | ------ | -------------------- |
| `attributes.long_task.id`                       | ![Stable](https://img.shields.io/badge/-stable-lightgreen)      | str    | 长任务或长动画帧 ID          |
| `attributes.long_task.name`                     | ![Stable](https://img.shields.io/badge/-stable-lightgreen)      | str    | Performance Entry 名称 |
| `attributes.long_task.entry_type` *[1]*         | ![Stable](https://img.shields.io/badge/-stable-lightgreen)      | str    | 采集条目类型               |
| `attributes.long_task.blocking_duration`        | ![Stable](https://img.shields.io/badge/-stable-lightgreen)      | number | 主线程阻塞耗时（ms）          |
| `attributes.long_task.first_ui_event_timestamp` | ![Stable](https://img.shields.io/badge/-stable-lightgreen)      | number | 首个 UI 事件时间（ms）       |
| `attributes.long_task.render_start`             | ![Stable](https://img.shields.io/badge/-stable-lightgreen)      | number | 渲染阶段开始时间（ms）         |
| `attributes.long_task.style_and_layout_start`   | ![Stable](https://img.shields.io/badge/-stable-lightgreen)      | number | 样式与布局阶段开始时间（ms）      |

**[1] `attributes.long_task.entry_type`**：

| 值                        | 描述                                                                  |
| ------------------------ | ------------------------------------------------------------------- |
| `long-animation-frame`   | 通过 Long Animation Frame API 采集，包含主线程阻塞、渲染、样式与布局阶段以及脚本归因信息。 |
| `long-task`              | 通过 Long Tasks API 采集，用于不支持 Long Animation Frame API 的浏览器，只提供长任务基础信息。 |

### n. custom

`reportCustomEvent()` 产生 `custom.<name>` Span。
