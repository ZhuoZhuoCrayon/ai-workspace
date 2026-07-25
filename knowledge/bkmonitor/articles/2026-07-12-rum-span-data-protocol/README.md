---
title: RUM 数据协议
tags: [rum, span, metric, log, data-protocol, opentelemetry, web]
description: 归档 bkmonitor RUM Web 的 Resource、Span、Metric 和 Log 协议，供数据上报、字段消费和协议核对使用。
created: 2026-07-12
updated: 2026-07-25
---
本文记录 `@blueking/open-telemetry` 当前上报的 Resource、Span、Metric 和 Log 字段。

| 状态                                                             | 描述             |
| -------------------------------------------------------------- | -------------- |
| ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | 已上报，保持现状。      |
| ![Deprecated](https://img.shields.io/badge/-deprecated-red)    | 已上报，但需要废弃。     |
| ![Development](https://img.shields.io/badge/-development-blue) | 新补充或字段位置变更。    |
| ![Backend](https://img.shields.io/badge/-backend-orange)       | 由后端生成，前端不直接上报。 |

原则：
* Aegis、DataDog 后续统一转成 Otel Span 协议，同领域字段尽量对齐前两个 SDK，需控制字段数量，避免出现需转换 150+ 字段的情况.
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
| `resource.session.sample_rate`                                                                                         |                                                                | number | Session 采样率 | 取值范围为 `0`～`1`。                                 |
| `resource.telemetry.sdk.version`                                                                                       | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | SDK 版本      | --                                             |
| [`resource.telemetry.sdk.language`](https://opentelemetry.io/docs/specs/semconv/resource/#telemetry-sdk)               | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | enum   | 语言          | `webjs`。                                       |
| `resource.telemetry.sdk.name` *[1]*                                                                                    | ![Development](https://img.shields.io/badge/-development-blue) | str    | SDK 名称      | --                                             |
| `resource.device.type`                                                                                                 | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | enum   | 设备类型        | `desktop`、`mobile`、`tablet`、`other`。           |
| `resource.user_agent.name`                                                                                             | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | 代理名称        | 通常指的是浏览器的名称，如 `Chrome`、`Edge`。                 |
| `resource.user_agent.version`                                                                                          | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | 代理版本        | 通常指的是浏览器的名称，如 `149`、`151`。                     |
| `resource.user_agent.os.name`                                                                                          | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | 操作系统名       | 如 `macOS`、`Windows`、`Android`。                 |
| `resource.device.memory_gib`                                                                                           | ![Deprecated](https://img.shields.io/badge/-deprecated-red)    | int    | 内存          |                                                |
**[1] `resource.telemetry.sdk.name`**：`blueking`（蓝鲸 Otel SDK，当前值为 @blueking/open-telemetry，需修改。）｜aegis（Aegis SDK）。

### c. Status

| 字段               | 状态                                                         | 类型  | 描述   | 备注                           |
| ---------------- | ---------------------------------------------------------- | --- | ---- | ---------------------------- |
| `status.code`    | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 状态码  | 0（未设置）<br />1（正常）<br />2（异常） |
| `status.message` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 状态描述 | 如 `Failed to fetch`          |

### d. Event

| 字段                                                                      | 状态                                                         | 类型     | 描述            | 备注                   |
| ----------------------------------------------------------------------- | ---------------------------------------------------------- | ------ | ------------- | -------------------- |
| `events[].name` *[1]*                                                   | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str    | 事件发生时间（微秒）    |                      |
| `events[].timestamp`                                                    | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int    | 事件事件          |                      |
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

| 字段                    | 状态                                                         | 类型  | 描述         | 备注  |
| --------------------- | ---------------------------------------------------------- | --- | ---------- | --- |
| `events[].name` *[1]* | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 事件发生时间（微秒） |     |

## 0x02 Attributes

### a. 基础字段

| 字段                             | 状态                                                         | 类型 | 描述          | 备注           |
| ------------------------------ | ---------------------------------------------------------- | ---- | ----------- | ------------ |
| `attributes.user.id`           | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str  | 用户 ID       | --           |
| `attributes.span_type` *[1]*   | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | enum | Span 类型     | --           |
| `attributes.outcome.type`      |                                                            | enum | 执行结果        | `success`、`warning`、`error`、`timeout`、`abort`。 |
| `attributes.outcome.reason`    |                                                            | str  | 结果原因        | 非正常结果的低基数原因。 |
| `attributes.document.referrer` |                                                            | str  | 文档 referrer | 仅初始加载上报。    |

**[1] `attributes.span_type`**：

| 值          | 描述                     |
| ---------- | ---------------------- |
| `session`  | Session 创建、轮换或结束。     |
| `view`     | 页面首次加载或路由视图生命周期。      |
| `resource` | 静态资源、Fetch 或 XHR 请求。   |
| `error`    | 浏览器错误、白屏或 CSP 违规。     |
| `vital`    | Web Vitals 指标。          |
| `long_task` | Long Task 或长动画帧。       |
| `action`   | 用户交互或主动上报的 Action。     |
| `websocket` | WebSocket 生命周期事件。      |
| `custom`   | 主动上报的自定义事件。            |

### b. [error](https://opentelemetry.io/docs/specs/semconv/registry/attributes/error/)


| 字段                                         | 状态                                                             | 类型      | 描述         | 备注                                                                   |
| ------------------------------------------ | -------------------------------------------------------------- | ------- | ---------- | -------------------------------------------------------------------- |
| `attributes.error.type`                    | ![Development](https://img.shields.io/badge/-development-blue) | str     | 低基数错误类型    | --                                                                   |
| `attributes.error.message`                 | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str     | 错误信息       | --                                                                   |
| `attributes.error.handled`                 | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | boolean | 错误是否被捕获    | --                                                                   |
| `attributes.error.source`                  | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str     | 错误来源       | 枚举值：<br/>- window.error（固定值）<br/>- resource<br/>- unhandledrejection |
| `attributes.code.column`                   | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | int     | 代码列号       |                                                                      |
| `attributes.code.filepath`                 | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str     | 代码文件路径     |                                                                      |
| `attributes.code.lineno`                   | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | int     | 代码行号       |                                                                      |
| `attributes.html.tag`                      | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str     | 关联 HTML 标签 | 资源类错误时出现，例如 `IMG`                                                    |
| `attributes.error.cross_origin`            | ![Deprecated](https://img.shields.io/badge/-deprecated-red)    | boolean | 跨域脚本错误     | --                                                                   |
### d. [browser](https://opentelemetry.io/docs/specs/semconv/registry/attributes/browser/)

| 字段                                   | 状态                                                         | 类型  | 描述      | 备注                           |
| ------------------------------------ | ---------------------------------------------------------- | --- | ------- | ---------------------------- |
| `attributes.browser.screen.height`   | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 屏幕尺寸的高度 | Aegis 使用 `sr = 1728 * 1117`。 |
| `attributes.browser.screen.width`    | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 屏幕尺寸的宽度 | --                           |
| `attributes.browser.viewport.height` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 视口尺寸的高度 | Aegis 使用 `vp = 576 * 918`。   |
| `attributes.browser.viewport.width`  | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int | 视口尺寸的宽度 | --                           |

### e. [device](https://opentelemetry.io/docs/specs/semconv/registry/attributes/device/)

| 字段                     | 状态                                                         | 类型  | 描述   | 备注                                        |
| ---------------------- | ---------------------------------------------------------- | --- | ---- | ----------------------------------------- |
| `attributes.device.id` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str | 设备标识 | 如 `fd136680-a37b-45ea-80ee-365bfdc7f82e`。 |

### f. [network](https://opentelemetry.io/docs/specs/semconv/registry/attributes/network/)

| 字段                                   | 状态                                                             | 类型   | 描述      | 备注                                                          |
| ------------------------------------ | -------------------------------------------------------------- | ---- | ------- | ----------------------------------------------------------- |
| `attributes.network.connection.type` | ![Development](https://img.shields.io/badge/-development-blue) | str  | 连接类型    | --<br><br>                                                  |
| `attributes.network.effective_type`  | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str  | 有效网络质量  | --                                                          |
| `attributes.network.status`          |                                                                | enum | 网络连接状态  | `connected`、`not_connected`。                                |
| `attributes.network.protocol.name`   | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | enum | 应用层网络协议 | 仅 WebSocket Span 上报，固定为 `websocket`；HTTP Resource Span 不上报。 |

**[1] `attributes.network.connection.type`**：表示设备当前使用的物理网络连接方式，不一定存在，等同与 DataDog（`connectivity.interfaces`）、Aegis（`netType`）。

Aegis 将「连接类型」「网络质量」整合成 `netType`（`wifi`、`wired`、`2G`、`3G`、`5G`、`6G`），不推荐这种做法。

| 值         | 描述         | 备注                                  |
| --------- | ---------- | ----------------------------------- |
| `wifi`    | Wi-Fi 无线网络 | 仅表示通过 Wi-Fi 连接，不代表网络一定快。            |
| `cell`    | 蜂窝移动网络     | 可能是 2G、3G、4G 或 5G，不表示具体代际。          |
| `wired`   | 有线网络       | 通过网线或有线网卡连接，Aegis 的 `wired` 应映射为该值。 |
| `unknown` | 未知         | 浏览器不支持、无法识别，或者连接方式不在支持范围内；不表示已经断网。  |

**[2] `attributes.network.effective_type`**：表示浏览器根据延迟和下载速度估算出的实际网络质量，等同与 DataDog（`connectivity.effective_type`）、Aegis（`netType`）。

| 值         | 描述   | 备注                         |
| --------- | ---- | -------------------------- |
| `slow-2g` | 极慢网络 | 页面和图片加载非常慢，通常只能满足少量文本传输。   |
| `2g`      | 较慢网络 | 简单页面可以打开，图片、脚本和接口请求可能明显缓慢。 |
| `3g`      | 中等网络 | 普通网页基本可用，但大资源和复杂页面仍可能等待。   |
| `4g`      | 较快网络 | 延迟和带宽表现较好，适合大多数 Web 应用。    |

### g. session

| 字段                                      | 状态                                                         | 类型      | 描述        | 备注                 |
| --------------------------------------- | ---------------------------------------------------------- | ------- | --------- | ------------------ |
| `attributes.session.has_replay`         | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | boolean | 是否回放      | --                 |
| `attributes.session.id`                 | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | 会话唯一标识    | --                 |
| `attributes.session.start_time`         |                                                            | number  | 会话开始时间    | Unix 毫秒时间戳。        |
| `attributes.session.type`               |                                                            | enum    | 会话类型      | 当前固定为 `user`。      |
| `attributes.session.phase` *[1]*        |                                                            | enum    | 会话生命周期阶段 | --                 |
| `attributes.session.lifecycle.reason`   |                                                            | str     | 生命周期原因    | 如 `init`、`inactivity`、`maxLifetime`、`external`。 |
| `attributes.session.previous_id`        |                                                            | str     | 前一个会话 ID  | Session 轮换时出现。    |

**[1] `attributes.session.phase`**：

| 值       | 描述                     |
| ------- | ---------------------- |
| `start` | 创建首个 Session。          |
| `rotate` | 旧 Session 到期后创建新 Session。 |
| `end`   | 当前 Session 结束。          |

### i. view

| 字段                                    | 状态                                                             | 类型     | 描述                      | 备注                                            |
| ------------------------------------- | -------------------------------------------------------------- | ------ | ----------------------- | --------------------------------------------- |
| `attributes.view.id`                  | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | 视图 ID                   |                                               |
| `attributes.view.name`                | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | 视图名称                    | 如 `/apm/home`。                                |
| `attributes.view.loading_type`        | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | 视图加载类型                  | --                                            |
| `attributes.view.url`                 | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | 视图 URL                  | 如 `https://example.com/cur`。                  |
| `attributes.view.previous`            | ![Development](https://img.shields.io/badge/-development-blue) | str    | 视图 URL（前一个）             | 如 `https://example.com/pre`。                  |
| `attributes.view.url_path_group`      | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | 视图路径分组                  | 如 `/apm/home`。                                |
| `attributes.view.loading_time`        | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | number | 视图加载耗时（ms）              | 加载时间计算完成后上报。                                  |
| `attributes.view.loading_time_source` |                                                                | enum   | 视图加载耗时来源                | `auto`、`manual`。                             |
| `attributes.view.first_byte`          | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | number | 首字节时间（ms）               | 仅初始导航存在。                                      |
| `attributes.view.dom_interactive`     | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | number | DOM 可交互时间（ms）           | 仅初始导航存在。                                      |
| `attributes.view.dom_content_loaded`  | ![Stable\|43](https://img.shields.io/badge/-stable-lightgreen) | number | DOMContentLoaded 时间（ms） | 仅初始导航存在。                                      |
| `attributes.view.dom_complete`        | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | number | DOM Complete 时间（ms）     | 仅初始导航存在。                                      |
| `attributes.view.load_event`          | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | number | Load Event 时间（ms）       | 仅初始导航存在。                                      |
| `attributes.view.phase`               | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | enum   | 视图生命周期阶段                | 枚举值：<br>- start<br>- update<br>- end          |
| `attributes.view.started_at`          | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | number | 视图开始时间（ms）              | 取 `performance.timeOrigin`。                   |
| `attributes.view.version`             | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | int    | 视图事件版本号                 | 同一 `attributes.view.id` 从 `1` 开始递增，用于排序和幂等合并。 |
| `attributes.view.end_reason`          | ![Stable](https://img.shields.io/badge/-stable-lightgreen)     | str    | 结束原因                    | --                                            |



**[1] `attributes.view.name`**：默认取 `view.url_path_group`，也可由 `startView({ name })` 或 `setViewName` 设置。

**[2] `attributes.view.loading_type`**：

| 值                 | 描述              |
| ----------------- | --------------- |
| `initial_load`    | 首次页面加载（初始导航）    |
| `route_change`    | SPA 路由切换        |
| `session_renewal` | 会话续期后重建         |
| `bf_cache`        | 从浏览器 BFCache 恢复 |

**[3] `attributes.view.url_path_group`**：用于聚合的页面路径，默认只是 URL pathname，不会自动将数字、UUID 替换为 `:id`，需要接入方配置分组逻辑。

**[3]【有风险】 `attributes.view.phase`**：当前 View Span 的生命周期阶段，Schema v3 不再用一条长 Span 表达整个 View，而是发送多条瞬时生命周期 Span。


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

### j. resource


| 字段                                           | 状态                                                         | 类型      | 描述                  | 备注                                                                      |
| -------------------------------------------- | ---------------------------------------------------------- | ------- | ------------------- | ----------------------------------------------------------------------- |
| `attributes.resource.type`                   | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | enum    | 资源类型                | --                                                                      |
| `attributes.resource.size`                   | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int     | 资源大小                | --                                                                      |
| `attributes.resource.transfer_size`          | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int     | 传输大小                | --                                                                      |
| `attributes.resource.decoded_body_size`      | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int     | 解码后正文大小             | --                                                                      |
| `attributes.resource.encoded_body_size`      | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | int     | 编码后正文大小             | --                                                                      |
| `attributes.resource.protocol`               | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | 传输协议                | 浏览器提供下一跳协议时存在，如 `h2`、`h3`、`http/1.1`。                                   |
| `attributes.resource.cache.hit`              | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | boolean | 是否缓存命中              | --                                                                      |
| `attributes.resource.delivery_type`          | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | 交付类型                | 浏览器提供交付类型时存在，如 `cache`、`navigational-prefetch`、`cache-storage`、`other`。 |
| `attributes.resource.render_blocking_status` | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | enum    | 渲染阻塞状态              | 浏览器提供渲染阻塞状态时存在，枚举值为 `blocking`、`non-blocking`                           |
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

### r. action

| 字段                                    | 状态                                                         | 类型     | 描述                                          |
| ------------------------------------- | ---------------------------------------------------------- | ------ | ------------------------------------------- |
| `attributes.action.id`                | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str    | --                                          |
| `attributes.action.type`              | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str    | 动作类型                                        |
| `attributes.action.name`              | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str    | 动作名称                                        |
| `attributes.action.target.name`       | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str    | 目标元素名称                                      |
| `attributes.action.target.tag`        | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str    | 目标元素标签                                      |
| `attributes.action.loading_time`      | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number | 点击后页面活动稳定耗时（ms）                             |
| `attributes.action.frustration.type`  | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str[]  | 枚举值：`rage_click`、`dead_click`、`error_click` |


### l. http & [url](https://opentelemetry.io/docs/specs/semconv/registry/attributes/url/) & server

| 字段                                     | 状态                                                          | 类型  | 描述      |                              |
| -------------------------------------- | ----------------------------------------------------------- | --- | ------- | ---------------------------- |
| `attributes.url.full`                  | ![Stable](https://img.shields.io/badge/-stable-lightgreen)  | str | 完整 URL  | 如 `https://example.com/apm`。 |
| `attributes.url.previous`              | ![Deprecated](https://img.shields.io/badge/-deprecated-red) | str | 前一个 URL | --                           |
| `attributes.url.scheme`                | ![Stable](https://img.shields.io/badge/-stable-lightgreen)  | str | 协议      | 如 `ws`、`wss`。                |
| `attributes.http.request.method`       | ![Stable](https://img.shields.io/badge/-stable-lightgreen)  | str | 请求方法    | 如 `GET`、`POST`。              |
| `attributes.http.response.status_code` | ![Stable](https://img.shields.io/badge/-stable-lightgreen)  | int | 返回码     | 如 `200`、`404`。               |
| `attributes.server.address`            | ![Stable](https://img.shields.io/badge/-stable-lightgreen)  | str | 地址      | 如 `example.com`。             |
| `attributes.server.port`               | ![Stable](https://img.shields.io/badge/-stable-lightgreen)  | int | 端口      | --                           |



### o. vital

| 字段                        | 状态                                                          | 类型     | 描述         | 备注                                     |
| ------------------------- | ----------------------------------------------------------- | ------ | ---------- | -------------------------------------- |
| `attributes.vital.id`     | ![Stable](https://img.shields.io/badge/-stable-lightgreen)  | str    | Vital 唯一标识 |                                        |
| `attributes.vital.metric` | ![Stable](https://img.shields.io/badge/-stable-lightgreen)  | enum   | 指标名        |                                        |
| `attributes.vital.value`  | ![Stable](https://img.shields.io/badge/-stable-lightgreen)  | number | 指标测量值      | CLS 单位为 `1`，FCP、INP、LCP、TTFB 单位为 `ms`。 |
| `attributes.vital.rating` | ![Deprecated](https://img.shields.io/badge/-deprecated-red) | str    | 评级         | --                                     |
|                           |                                                             |        |            |                                        |

**[1] `attributes.vital.metric`**：

| 值    | 描述                                                                    | 备注                                        |
| ---- | --------------------------------------------------------------------- | ----------------------------------------- |
| cls  | [累积布局偏移（Cumulative Layout Shift）](https://web.dev/articles/cls)       | 一个以用户为中心的重要指标，用于衡量视觉稳定性                   |
| inp  | [交互到下一次绘制（Interaction to Next Paint）](https://web.dev/articles/inp)   | 稳定的核心网页指标，使用 Event Timing API 中的数据来评估响应速度 |
| lcp  | [最大内容绘制（Largest Contentful Paint, LCP）](https://web.dev/articles/lcp) | Core Web Vital 中的一个重要且稳定的指标，用于衡量页面加载的速度。  |
| fcp  | [首次内容绘制（First Contentful Paint）](https://web.dev/articles/fcp)        | 是一项以用户为中心的重要指标，用于衡量用户感知的加载速度              |
| ttfb | [首字节时间（Time to First Byte）](https://web.dev/articles/ttfb)            | 是指从浏览器发起请求到接收到服务器返回第一个数据字节所经过的时间          |
|      |                                                                       |                                           |


- vital.metric=cls

| 字段                                          | 类型     | 描述             | 备注                                                                                                                              |
| ------------------------------------------- | ------ | -------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `attributes.vital.cls.largest_shift_target` | str    | 最大单次布局偏移来源元素标识 | 高基数字段，依次取 `data-bk-action-name`、`aria-label`、`name`，最后回退到小写标签名；不是 CSS 选择器。                                                      |
| `attributes.vital.cls.largest_shift_value`  | number | 最大单次布局偏移分值     | 该元素造成的单次最大偏移分数，注意这是"最大一次"的分数，不是 CLS 累积总分（总分在 vital.value 和 target_value 里）。值越小越好，接近 0 为优                                        |
| `attributes.vital.cls.load_state`           | str    | 最大偏移发生时的页面     | 枚举值：<br/>- loading<br/>- dom-interactive<br/>- dom-content-loaded<br/>- complete<br/>用于判断 CLS 偏移发生在首屏哪个时期（体验越差时越可能在 loading 阶段） |

- vital.metric=inp

| 字段                                         | 类型     | 描述           | 备注                                                                         |
| ------------------------------------------ | ------ | ------------ | -------------------------------------------------------------------------- |
| `attributes.vital.inp.input_delay`         | number | 输入延迟（ms）     | 用户发起交互（如点击）到事件处理器开始执行的等待时间，反映主线程繁忙程度                                       |
| `attributes.vital.inp.interaction_target`  | str    | INP 交互目标元素标识 | 高基数字段，依次取 `data-bk-action-name`、`aria-label`、`name`，最后回退到小写标签名；不是 CSS 选择器。 |
| `attributes.vital.inp.interaction_type`    | str    | 交互类型         | 用户触发方式，如  `keyup`、`pointerdown`、`pointerup` 等事件名。                          |
| `attributes.vital.inp.presentation_delay`  | number | 呈现延迟（ms）     | 事件处理回调完成之后，到浏览器实际渲染下一帧的耗时，CSS/布局/重绘瓶颈看这里                                   |
| `attributes.vital.inp.processing_duration` | number | 处理耗时（ms）     | 事件处理回调（如 click handler）本身的执行时间，JS 逻辑过重时这个值会变大                              |

- vital.metric=lcp

| 字段                                            | 类型     | 描述                  | 备注                                                                                                     |
| --------------------------------------------- | ------ | ------------------- | ------------------------------------------------------------------------------------------------------ |
| `attributes.vital.lcp.element_render_delay`   | number | LCP 元素的渲染阻塞延迟（ms）   | [a] LCP 元素资源加载完成后，到浏览器真正渲染该元素之间的等待时间<br/>[b] 主要由主线程阻塞（长任务/JS 执行）导致<br/>[c] 值越小越好                       |
| `attributes.vital.lcp.resource_load_duration` | number | LCP 资源加载耗时（ms）      | [a] LCP 元素依赖的外部资源（图片/字体等）从请求到下载完成的时间<br/>[b] 如果 LCP 是纯文本节点，此项可能缺失<br/>[c] 用于排查 CDN/网络/资源体积问题           |
| `attributes.vital.lcp.target`                 | str    | LCP 目标元素的 DOM 选择器   | 高基数字段，LCP 候选元素的 CSS 选择器路径，如 `html > body > div#hero > img`                                             |
| `attributes.vital.lcp.time_to_first_byte`     | number | LCP 发生前的 TTFB（ms）   | [a] 从导航开始到收到首字节的耗时<br/>[b] 这是 LCP 的"基座"——如果 TTFB 本身就很高，后面两段也会相应推迟<br/>[c] LCP ≈ TTFB + 资源加载耗时 + 元素渲染延迟 |
| `attributes.vital.lcp.url`                    | str    | LCP 元素对应资源 URL（已脱敏） | 高基数字段，LCP 为图片/背景图/视频海报等资源时，这里是该资源的地址；如果 LCP 是文本节点，此项缺失。用于定位是哪张图片拖慢了首屏                                  |

- vital.metric=fcp

| 字段                                        | 类型     | 描述                | 备注                                                                                                             |
| ----------------------------------------- | ------ | ----------------- | -------------------------------------------------------------------------------------------------------------- |
| `attributes.vital.fcp.load_state`         | str    | FCP 发生时的页面加载阶段    | 枚举值：<br/>- loading<br/>- dom-interactive<br/>- dom-content-loaded<br/>- complete<br/>用于判断首次内容绘制发生在页面加载的哪个时期    |
| `attributes.vital.fcp.time_to_first_byte` | number | FCP 发生前的首字节时间（ms） | [a] 从导航开始到收到服务器首个响应字节的耗时<br/>[b] FCP 不可能早于 TTFB，此值揭示了"网络基座"耗时<br/>[c] 当 FCP 延迟过高时，若此值大说明是服务端/网络问题，若小则可能是前端渲染阻塞 |

- vital.metric=ttfb

| 字段                                          | 类型  | 描述                   | 备注                                                           |
|---------------------------------------------|-----|----------------------|--------------------------------------------------------------|
| `attributes.vital.ttfb.waiting_duration`    | number | 请求就绪后的等待耗时（ms）       | 主要包括重定向处理、Service Worker 启动处理、请求排队                           |
| `attributes.vital.ttfb.dns_duration`        | number | DNS 解析耗时（ms）         | 解析慢通常由 DNS 服务器延迟、复杂 CNAME 链或本地 DNS 缓存失效导致。多国/多地域部署时此值可能偏高    |
| `attributes.vital.ttfb.connection_duration` | number | TCP + TLS 连接建立耗时（ms） | 包含 TCP 三次握手和 TLS/SSL 协商。HTTPS 强制、TLS 1.3 升级、CDN 边缘节点距离都会影响此值 |
| `attributes.vital.ttfb.request_duration`    | number | 请求发送后等待首字节耗时（ms）     | 导航请求的发送报文极小，此值主要反映网络往返 RTT 与服务器从接到请求到吐出首字节的时间                |


- span_name == browser.blank_screen

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

- span_name == csp.violation

| 字段                                   | 类型  | 描述               | 备注  |
| ------------------------------------ | --- | ---------------- | --- |
| `attributes.csp.blocked_uri`         | str | 被拦截资源（URL 类值已脱敏） |     |
| `attributes.csp.violated_directive`  | str | 违反的指令            |     |
| `attributes.csp.effective_directive` | str | 生效的指令            |     |
| `attributes.csp.disposition`         | str | enforce / report |     |
| `attributes.csp.source_file`         | str | 触发脚本（已脱敏）        |     |
| `attributes.csp.line_number`         | int | 触发位置行号           |     |
| `attributes.csp.column_number`       | int | 触发位置列号           |     |
| `attributes.csp.status_code`         | int | 状态码              |     |
| `attributes.csp.original_policy`     | str | 完整策略，仅窗口首条携带     |     |
|                                      |     |                  |     |

### q. longtask

| 字段                                                              | 状态                                                         | 类型      | 描述                                     |
| --------------------------------------------------------------- | ---------------------------------------------------------- | ------- | -------------------------------------- |
| `attributes.long_task.id`                                       | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | 长任务或长动画帧 ID                            |
| `attributes.long_task.name`                                     |                                                            | str     | Performance Entry 名称                    |
| `attributes.long_task.entry_type`                               | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | str     | 枚举值：`long-animation-frame`、`long-task` |
| `attributes.long_task.start_time`                               | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 相对 `performance.timeOrigin` 的开始时间（ms）  |
| `attributes.long_task.duration`                                 | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 总耗时（ms）                                |
| `attributes.long_task.blocking_duration`                        | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 主线程阻塞耗时（ms）                            |
| `attributes.long_task.first_ui_event_timestamp`                 | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 首个 UI 事件时间（ms）                         |
| `attributes.long_task.render_start`                             | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 渲染阶段开始时间（ms）                           |
| `attributes.long_task.style_and_layout_start`                   | ![Stable](https://img.shields.io/badge/-stable-lightgreen) | number  | 样式与布局阶段开始时间（ms）                        |



### t. custom

`reportCustomEvent()` 产生 `custom.<name>` Span。
