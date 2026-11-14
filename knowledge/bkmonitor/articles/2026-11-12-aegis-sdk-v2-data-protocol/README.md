---
title: Aegis SDK v2 数据协议
tags: [rum, aegis, web, data-protocol, session, performance]
description: 说明 Aegis Web SDK 的上报字段、取值含义，以及会话、页面、操作、请求和性能数据的采集机制。
created: 2026-11-12
updated: 2026-11-12
---

# Aegis SDK v2 数据协议

本文说明 Aegis 在浏览器中记录哪些数据、每个字段代表什么，以及这些数据如何还原一次用户访问。内容基于 `2026-11-12` 获取的 [Aegis Web SDK 2.5.38](https://aegis.cdn-go.cn/aegis-sdk-v2/2.5.38/aegis.min.js)，与当日 [latest 版本](https://aegis.cdn-go.cn/aegis-sdk-v2/latest/aegis.min.js) 一致。

## 0x01 用户访问模型

```text
Session：用户的一段连续访问
│
├── View：订单列表页
│   ├── 页面性能：多久出现内容、页面是否卡顿或跳动
│   ├── Resource：加载脚本、样式和图片
│   └── Action：点击“查询订单”
│       ├── API：请求订单接口
│       └── Error：请求或页面执行过程中发生的错误
│
└── View：订单详情页
    └── Action：点击“提交订单”
        └── API：提交订单接口
```

Session（会话）、View（页面）和 Action（操作）分别回答“哪次访问”“哪个页面”和“哪次操作”。接口、错误等记录携带采集时的这些 ID，查询时便能把同一次访问中的事件串起来。

Aegis 通过插件开启各类采集。未启用 Session 插件时，仍可收到页面性能和错误日志，但这些记录不带自动生成的会话、页面和操作 ID。

## 0x02 公共字段

### a. 上报结构

```json
{
  "topic": "example-project",
  "scheme": "v2",
  "bean": { "uid": "user-1", "version": "2.5.38", "env": "production" },
  "ext": "{\"release\":\"1.0.0\"}",
  "d2": [
    {
      "fields": "{\"from\":\"https://example.com/orders\",\"type\":\"pv\",\"level\":\"info\",\"plugin\":\"pv\"}",
      "message": [
        "{\"msg\":\"pv\",\"timestamp\":1800000000000,\"aegisv2_goto\":\"2222222222222222\"}"
      ]
    }
  ]
}
```

| 字段 | 类型 | 描述 | 说明 |
| --- | --- | --- | --- |
| `topic` | str | 接收数据的项目 ID | 来自初始化配置 `id`。 |
| `scheme` *[4]* | enum | 上报协议版本 | 用于识别整份请求的数据结构。 |
| `bean` | object | 这批数据共用的用户、设备和环境信息 | 例如用户 ID、操作系统、屏幕尺寸。 |
| `ext` *[1]* | str | 这批数据共用的业务扩展信息 | JSON 字符串，未设置时为 `"{}"`。 |
| `d2` *[2]* | object[] | 本次发送的事件分组 | 同一请求可以携带多个分组。 |
| `d2[].fields` *[3]* | str | 事件发生时的页面、会话和分类信息 | JSON 字符串，同组事件共用。 |
| `d2[].message` | str[] | 每条事件的具体内容 | 每个数组元素都是一段 JSON 字符串。 |

**[1] `ext`**：保存 `config.extField` 中的业务标签，例如应用发布版本、渠道或租户。它作用于整批数据，单次事件的订单号等信息应放在该事件的扩展字段中。

**[2] `d2`**：SDK 先暂存事件，再合并发送，以减少上报请求数。默认在最近一批事件进入队列后等待 `1 s`，期间有新事件会重新计时，累计到 `400` 条或触发立即发送时提前发出。

```text
采集事件 → 暂存并合批 → 按插件采样 → 按相同 fields 分组 → 发送请求
```

常规上报使用 XHR。离开页面等触发立即发送的场景可使用 [Beacon API](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/sendBeacon)，由浏览器安排小批量数据发送；浏览器接受 Beacon 请求不等于服务端已收到数据。

**[3] `d2[].fields`**：同组事件拥有完全相同的上下文，例如同一个页面、同一个操作和同一种日志级别。SDK 在采集时保存这份信息，所以即使稍后才发送，也能保留当时的页面归属。

正文用 `fields.xxx` 和 `message.xxx` 表示解码后的字段，读取方式如下：

```text
fields  = JSON.parse(d2[i].fields)
message = JSON.parse(d2[i].message[j])
ext     = JSON.parse(ext)
```

`bean` 和 `ext` 在发送前组装。如果用户在等待发送期间登录或切换账号，尚未发出的记录可能使用更新后的 `bean.uid`。

**[4] `scheme`**：标记请求采用哪种数据结构，与 SDK 软件版本 `2.5.38` 的含义不同。本版本只产生以下值。

| 值 | 描述 |
| --- | --- |
| `v2` | 使用 `bean` 保存公共信息，使用 `d2` 分组保存事件。 |

### b. 用户、设备与环境

| 字段                    | 类型   | 描述             | 说明                                   |
| --------------------- | ---- | -------------- | ------------------------------------ |
| `bean.uid` *[1]*      | str  | 业务用户 ID        | 由应用设置，例如登录账号 ID，默认空字符串。              |
| `bean.aid` *[1]*      | str  | 浏览器匿名 ID       | 由 `aid` 插件生成或读取，适合关联未登录访问。           |
| `bean.version` *[2]*  | str  | 版本标签           | 默认 `2.5.38`，可通过 `config.version` 修改。 |
| `bean.env` *[3]*      | str  | 应用运行环境         | 默认 `production`。                     |
| `bean.platform` *[4]* | enum | 用户设备的操作系统      | 由 `device` 插件识别。                     |
| `bean.netType` *[5]*  | enum | 用户访问时的网络情况     | 例如 `wifi`、`4G` 或 `unknown`。          |
| `bean.vp` *[7]* | str | 浏览器页面视口的宽高 | 例如 `1440 * 900`，不包含浏览器工具栏。 |
| `bean.sr` *[7]* | str | 屏幕宽高 | 例如 `1920 * 1080`，使用浏览器报告的屏幕尺寸。 |
| `bean.referer` *[6]*  | str  | 用户打开当前文档前的来源地址 | 取 `document.referrer`，可能为空。          |
| `bean.from`           | str  | 业务手动设置的来源      | 可选，自动采集的页面地址见 `fields.from`。         |
| `bean.sessionId`      | str  | 业务手动设置的会话标识    | 可选，自动会话 ID 见 `fields.session.id`。    |
| `ext.wechatVersion`   | str  | 微信客户端版本        | 仅识别到微信浏览器时提供，例如 `8.0.50`。            |
| `ext.<业务字段>`          | any  | 业务附加标签         | 由 `config.extField` 设置。              |

**[1] `bean.uid` 与 `bean.aid`**：`uid` 用来识别业务账号，`aid` 用来关联同一浏览器中的访问。两者同时保留，可以区分“同一个账号换了设备”和“同一浏览器切换了账号”。

```text
读取 plugin.aid 中手动指定的 ID
              ↓ 未指定
读取浏览器 localStorage 中的 AEGIS_ID
              ↓ 不存在
生成随机 ID → 保存到 AEGIS_ID → 后续访问继续使用
```

[localStorage（浏览器本地存储）](https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage) 可以跨页面刷新保存数据，清理站点存储或换用浏览器后，匿名 ID 可能变化。因此 `aid` 不是设备硬件编号。

**[2] `bean.version`**：未配置时表示 SDK 的默认版本，配置后则表示应用传入的版本标签。查看数据时应结合接入配置理解，避免把业务版本误认为 SDK 版本。

**[3] `bean.env`**：用于把正式环境、测试环境等数据分开查看。SDK 提供以下环境名称，也允许应用传入自己的字符串。

| 值 | 描述 |
| --- | --- |
| `production` | 正式生产环境。 |
| `development` | 开发环境。 |
| `gray` | 灰度环境，供部分用户提前使用。 |
| `pre` | 预发布环境。 |
| `daily` | 日常集成环境。 |
| `local` | 本地运行环境。 |
| `test` | 测试环境。 |
| `others` | 其他环境。 |

**[4] `bean.platform`**：SDK 根据浏览器提供的 User-Agent 文本识别操作系统，自动采集会产生以下值。

| 值 | 描述 |
| --- | --- |
| `android` | Android。 |
| `iOS` | iPhone、iPad 等 iOS 设备。 |
| `windows` | Windows。 |
| `macOS` | macOS。 |
| `linux` | Linux。 |
| `other` | 未识别为上述系统。 |

**[5] `bean.netType`**：用于观察慢请求是否集中在某类网络下。SDK 优先读取 User-Agent 中的网络标记，否则使用浏览器的网络信息，默认每 `10 s` 刷新一次。

| 值 | 描述 |
| --- | --- |
| `wifi` | Wi-Fi 网络。 |
| `2G` | 2G 标记，或相当于 2G 的网络质量。 |
| `3G` | 3G 标记，或相当于 3G 的网络质量。 |
| `4G` | 4G 标记，或相当于 4G 的网络质量。 |
| `5G` | 从网络标记或自定义获取函数识别出的 5G。 |
| `6G` | 从网络标记或自定义获取函数识别出的 6G。 |
| `unknown` | 浏览器未提供可识别的信息。 |

浏览器的 [`effectiveType`](https://wicg.github.io/netinfo/#effective-connection-type-table) 根据延迟和下载速度估算网络质量。因此，连接 Wi-Fi 的用户也可能被记为 `4G`，该字段不能直接当作手机移动网络制式。

默认识别会把 `slow-2g` 和 `2g` 都归为 `2G`。应用也可通过 `getNetworkType` 提供取值；插件只接受上表中的名称，无法识别的值归为 `unknown`，不会自动保留 `wired` 等其他名称。

**[6] `bean.referer`**：记录打开这份网页文档的来源，例如用户从搜索结果进入订单页时的来源站点。单页应用内部切换路由不会重新加载文档，此值也不会跟着切换。

直接输入地址、从书签打开或受来源策略限制时，[`document.referrer`](https://developer.mozilla.org/en-US/docs/Web/API/Document/referrer) 可能为空。页面内部的上一页地址另见 `fields.view.referer`。

**[7] `bean.vp` 与 `bean.sr`**：`vp` 来自 `window.innerWidth/innerHeight`，`sr` 来自 `window.screen.width/height`，SDK 将宽高分别取整后用 ` * ` 拼接。

[`innerWidth`](https://developer.mozilla.org/en-US/docs/Web/API/Window/innerWidth) 描述页面布局视口，并包含垂直滚动条占用的宽度。设备插件在初始化时读取尺寸，没有随窗口缩放自动刷新，因此这些字段适合描述接入时的窗口和屏幕，不能用于还原每次操作的实时可见范围。

### c. 事件上下文

| 字段 | 类型 | 描述 | 说明 |
| --- | --- | --- | --- |
| `fields.from` *[1]* | str | 事件所在的页面地址 | 例如 `https://example.com/orders?page=1`。 |
| `fields.type` *[2]* | enum | 这条记录属于哪类数据 | 区分接口、性能、错误日志和自定义事件等。 |
| `fields.level` *[3]* | enum | 普通日志或具体错误类别 | 普通记录通常为 `info`。 |
| `fields.plugin` *[4]* | enum | 哪个插件采集了这条记录 | 例如 `api`、`assetSpeed`、`session`。 |
| `fields.session` | object | 当前会话信息 | 开启 Session 采集后提供。 |
| `fields.view` | object | 当前页面信息 | 开启 Session 采集后提供。 |
| `fields.action` | object | 当前正在进行的操作 | 仅存在可关联的 Action 时提供。 |

**[1] `fields.from`**：默认使用当前完整 URL，也可由 `pageUrl` 指定，或由 `urlHandler()` 返回。最多保留 `2,048` 个字符，默认保留查询参数和路径中的数字 ID。

SPA（单页应用）是在同一网页中切换界面的应用。开启 `plugin.spa` 后，Aegis 在识别到页面变化时刷新 `from` 并记录一次 PV（页面访问）；未开启时，`from` 可以一直保留初始页面地址。

**[2] `fields.type`**：决定如何理解 `message` 中的字段。

| 值 | 描述 |
| --- | --- |
| `normal` | 普通日志、前端错误或白屏明细。 |
| `pv` | 页面访问记录，也用于白屏次数统计。 |
| `session` | 会话、页面或操作的开始和结束记录。 |
| `api` | 接口请求结果和耗时。 |
| `assets_speed` | 脚本、样式、图片等静态资源的加载结果和耗时。 |
| `page_performance` | 页面加载阶段与首屏耗时。 |
| `web_vitals` | 页面加载、交互和视觉稳定性指标。 |
| `custom_event` | 业务主动上报的事件，例如“订单提交成功”。 |
| `custom_time` | 业务主动上报的耗时，例如“导出报表耗时”。 |
| `websocket` | WebSocket 连接结果或错误。 |
| `sdk_error` | SDK 自身的诊断错误，发送到独立诊断项目。 |

以上是本 Web 版本内置采集路径使用的分类。通过 `report()` 自行指定类型时，还可能出现业务自定义值。

**[3] `fields.level`**：先区分正常记录和错误，再定位错误来自哪里。

| 值 | 描述 |
| --- | --- |
| `info` | 普通信息，例如成功请求和性能数据。 |
| `error` | JavaScript 执行错误，或接口业务返回码表示失败。 |
| `promise_error` | 异步任务失败后没有被应用处理。 |
| `ajax_error` | 接口发生网络错误、HTTP 错误或已配置上报的请求中止。 |
| `script_error` | JavaScript 文件加载失败。 |
| `css_error` | 样式文件加载失败。 |
| `image_error` | 图片加载失败。 |
| `media_error` | 音频或视频加载失败。 |
| `websocket_error` | WebSocket 连接或发送过程出错。 |
| `blank_screen` | 检测到疑似白屏。 |
| `custom_error` | 应用通过 `aegis.error()` 主动报告的错误。 |
| `sdk_error` | SDK 自身运行出错。 |

这些是自动采集和常用主动接口产生的值，`report()` 也可传入其他级别。`forceReportErrorLog=true` 会让 SDK 识别的错误跳过采样过滤，但本版本的识别集合不包含 `custom_error`。

**[4] `fields.plugin`**：用于识别数据来源。同样是 `assets_speed`，既可能来自静态资源观察，也可能来自被归类为资源的接口请求。

| 值                 | 采集内容                    | 默认开启 |
| ----------------- | ----------------------- | ---- |
| `pv`              | 首次页面访问。                 | 是    |
| `spa`             | 单页应用的页面访问变化。            | 否    |
| `error`           | JavaScript、异步任务和资源加载错误。 | 是    |
| `api`             | Fetch 和 XHR 请求。         | 否    |
| `assetSpeed`      | 静态资源加载。                 | 否    |
| `pagePerformance` | 页面加载阶段和首屏耗时。            | 是    |
| `webVitals`       | Web Vitals 性能指标。        | 是    |
| `session`         | 会话、页面和操作。               | 否    |
| `custom`          | 应用主动调用的上报接口。            | 是    |
| `blankScreen`     | 白屏检测。                   | 否    |
| `websocket`       | WebSocket 连接监控。         | 否    |

`aid` 和 `device` 也默认开启，用来补充用户、设备字段，不单独产生上述事件。

采样决定“采到的记录有多少会发出”。SDK 按插件分别读取采样率，并对每条记录随机判断，例如 `0.1` 表示每条约有 `10%` 的机会被保留，而不是每十条固定保留一条。

| 采样配置来源 | 生效方式 |
| --- | --- |
| 本地 `sample` | 提供默认采样率，未配置时为 `1`。 |
| 服务端采样配置 | SDK 根据项目 ID 和 `uid` 获取，可覆盖相应插件的采样率。 |
| 用户白名单 | 命中白名单且 `whiteList=true` 时，各插件采样率设为 `1`。 |

SPA 记录使用 PV 的采样率。最终采样率不随事件一并上报，所以仅凭一批数据无法准确反推原始访问量。

### d. 事件内容

| 字段 | 类型 | 描述 | 说明 |
| --- | --- | --- | --- |
| `message.timestamp` *[1]* | number | SDK 记录这条事件的时间 | Unix 毫秒时间戳，可能经过服务端时钟校正。 |
| `message.aegisv2_goto` *[2]* | str | 单条事件 ID | `16` 位十六进制字符串。 |
| `message.msg` *[3]* | any | 日志正文或事件标记 | 自动记录通常是字符串。 |
| `message.errorMsg` | str | 便于浏览和聚合的错误摘要 | 有错误摘要时提供。 |
| `message.<业务字段>` | any | 这条事件特有的业务信息 | 例如订单 ID、操作结果。 |

**[1] `message.timestamp`**：SDK 生成记录时保存本机时间，在组装发送请求时加上估算的服务器时间差，减少用户电脑时钟不准对事件排序的影响。接口在完成后才生成记录，因此接口的 `timestamp` 接近完成时间。

```text
用户电脑比服务器慢 2 秒
    ↓ SDK 通过控制请求估算时间差
记录时间 10:00:00.000 + 时间差 2,000 ms
    ↓
上报 timestamp 对应 10:00:02.000
```

时间差估算会扣除控制请求的服务端处理时间，并把剩余往返时间的一半作为单程网络耗时。未成功校正时使用本机时间；具体业务事件的发生时刻也可能早于 SDK 生成记录的时刻。

**[2] `message.aegisv2_goto`**：标识一条具体日志，用于关联详情，例如白屏记录通过 `linkLogId` 指向附近的一条错误。同一 View 的开始和结束各有自己的事件 ID，页面归属仍由 `fields.view.id` 表达。

**[3] `message.msg`**：性能记录常使用 `web_vitals` 等固定文字，错误记录则放入错误说明和调用堆栈。字段没有统一的内容格式，分类应以 `fields.type/level` 为准。

页面访问和性能记录的固定值如下；会话、资源、自定义事件和 WebSocket 的取值见各自小节。

| 值 | 使用场景 |
| --- | --- |
| `pv` | `pv` 插件记录的首次页面访问。 |
| `spa` | `spa` 插件记录的单页应用访问。 |
| `page_performance` | 页面加载阶段与首屏耗时。 |
| `web_vitals` | FCP、LCP 等用户体验指标。 |

白屏计数等记录可以不带 `msg`，自定义日志也可能传入对象。此版本没有对所有记录统一应用 `maxLength` 截断，接收数据时应允许正文长度不同。

## 0x03 会话、页面与操作

### a. Session（会话）

```json
{
  "fields": {
    "session": { "id": "11111111111111111111111111111111" },
    "type": "session", "level": "info", "plugin": "session"
  },
  "message": {
    "session_type": "session",
    "is_active": true,
    "session_from": "local_generate",
    "msg": "session",
    "timestamp": 1800000000000,
    "aegisv2_goto": "2222222222222222"
  }
}
```

示例展示解码后的字段，省略页面地址等公共信息。一个 Session 内可以浏览多个 View，每个 View 内可以进行多次 Action。

| 字段 | 类型 | 描述 | 说明 |
| --- | --- | --- | --- |
| `fields.session.id` *[1]* | str | 会话 ID | 将同一段访问中的页面、请求和错误关联起来。 |
| `message.session_type` *[2]* | enum | 本条开始或结束记录描述的对象 | 会话、页面或操作。 |
| `message.is_active` *[3]* | boolean | 对象正在开始还是结束 | 表示一次边界事件，不是持续更新的在线状态。 |
| `message.session_from` *[4]* | enum | 会话 ID 从哪里获得 | 页面和操作的开始、结束记录也带此字段。 |
| `message.msg` *[2]* | enum | 对象名称 | 与本条记录的 `session_type` 相同。 |

**[1] `fields.session.id`**：同一次连续访问共用这个 ID。SDK 默认在用户连续 `15 min` 没有活动后结束会话，即使用户一直操作，同一个会话最长也持续 `4 h`。

点击、触屏、按键和滚动都会延长不活跃截止时间，SDK 每 `1 s` 检查一次是否到期。会话过期后，下一次用户活动会创建新的 Session 和 View。

```text
10:00 打开页面     → Session S1 开始
10:05 点击按钮     → 不活跃截止时间延到 10:20
10:20 仍没有新操作 → S1 到期，结束当前操作、页面和会话
10:25 再次点击     → Session S2 开始，同一 URL 创建新的 View
```

Session 数据会经过两次采样判断，两次判断影响的范围不同：

| 判断时机 | 没有被选中时会怎样 |
| --- | --- |
| 收到采样配置时 | 停止 Session 插件并清除会话、页面和操作信息，后续由其他插件采集的事件不再自动带这些 ID。 |
| 一批记录准备发送时 | 分别判断是否保留每条记录，同一对象的开始和结束可能只留下其中一条。 |

因此，即使某个 Session 已有开始记录，也不保证会收到它的结束记录。缺少结束记录本身不表示用户仍在访问。

**[2] `message.session_type` 与 `message.msg`**：这三类记录都使用 `fields.type=session`，再通过 `session_type` 区分对象；`msg` 同时写入相同的值。

| 值 | 描述 |
| --- | --- |
| `session` | 一段用户访问的开始或结束。 |
| `view` | 一个页面的开始或结束。 |
| `action` | 一次操作的开始或结束。 |

**[3] `message.is_active`**：同一个对象的开始和结束使用相同对象 ID，例如同一个 `fields.view.id`。

| 值 | 描述 |
| --- | --- |
| `true` | 对象开始，例如用户进入页面。 |
| `false` | 对象结束，例如用户离开页面。 |

记录不直接提供持续时间，可以在收到完整开始、结束记录时按时间差估算。浏览器关闭和数据采样都可能导致记录不完整。

**[4] `message.session_from`**：首次创建会话时，SDK 按下表从上到下查找可用 ID，到期重建则直接本地生成。

| 值 | 描述 | 获取方式 |
| --- | --- | --- |
| `server_inject` | 由服务端把访问标识写入网页。 | 读取 `<meta name="traceparent">` 中的 Trace ID。 |
| `url_query` | 通过页面链接传递访问标识。 | 读取 URL 参数 `aegis_session_id`。 |
| `local_storage` | 使用浏览器中保存的访问标识。 | 读取本地存储项 `aegis_session_id`。 |
| `local_generate` | 没有使用外部标识，由 SDK 新建。 | 生成 `32` 位十六进制字符串。 |

例如服务端在网页中放入 `<meta name="traceparent" content="00-<Trace ID>-<Span ID>-01">`，SDK 会提取其中的 Trace ID 作为 Session ID。没有这个标记时才继续查找 URL 参数和本地存储；外部提供的 ID 不一定具有本地生成 ID 的格式。

本版本复用本地存储的条件是“存储的项目 ID 与当前项目不同”。因此刷新同一个项目的页面时，`aid` 可以保持不变，Session ID 仍可能重新生成。

### b. View（页面）

| 字段 | 类型 | 描述 | 说明 |
| --- | --- | --- | --- |
| `fields.view.id` *[1]* | str | 本次页面访问 ID | `16` 位十六进制字符串，同一 URL 的多次访问可以不同。 |
| `fields.view.view_name` *[2]* | str | 页面名称 | 创建 View 时读取网页标题，例如“订单列表”。 |
| `fields.view.view_url` *[3]* | str | 页面完整地址 | 例如 `https://example.com/orders/123?tab=detail`。 |
| `fields.view.loading_type` *[4]* | enum | 页面是如何创建的 | 首次加载或应用内路由切换。 |
| `fields.view.referer` *[5]* | str | 上一个 View 的页面地址 | 例如从订单列表进入详情时的列表地址。 |
| `fields.view.referrer` *[5]* | str | 初始来源的预留字段 | 初次创建和会话重建时为空字符串。 |

**[1] `fields.view.id`**：标识“这一次进入页面”，用于把页面内发生的操作、请求和错误放在一起。离开后再进入同一 URL，会创建新的 View ID。

```text
订单列表 View A
├── view / true：进入列表
├── action / true：点击订单
├── API 请求、错误等记录携带 View A
└── 切换到详情页
    ├── action / false：结束尚未完成的操作
    └── view / false：离开列表

订单详情 View B
└── view / true：进入详情，使用新的 View ID
```

接口通常在完成时关联当前页面。如果请求在列表页发出、切换到详情页后才完成，它可能携带详情页的 View ID。

**[2] `fields.view.view_name`**：来自 `document.title`，即浏览器标签页标题。SDK 在 View 创建时读取一次；应用稍后才修改标题时，已记录的名称不会自动更新。

**[3] `fields.view.view_url`**：保留原始地址，包括查询参数和路径中的 ID。`/orders/123` 与 `/orders/456` 会保留为两个地址，SDK 不自动改成 `/orders/:id`。

单页应用通过 [History API](https://developer.mozilla.org/en-US/docs/Web/API/History_API) 或 Hash（地址中 `#` 后的部分）切换页面。SDK 根据地址变化判断是否新建 View：

| 地址变化示例 | 是否新建 View | 原因 |
| --- | --- | --- |
| `/orders` → `/users` | 是 | 页面路径发生变化。 |
| `/orders?page=1` → `/orders?page=2` | 否 | 只改变查询参数。 |
| `/#/orders` → `/#/users` | 是 | Hash 路由改变，且不指向已有页面元素。 |
| `/#/orders?page=1` → `/#/orders?page=2` | 否 | Hash 去掉查询部分后相同。 |
| `/help` → `/help#faq`，页面存在 `id=faq` | 否 | 只是跳到当前页面的某个位置。 |

此版本监听 `hashchange` 并跟踪 `pushState/replaceState`，没有完整的 `popstate` 监听，因此浏览器前进、后退不一定创建新 View。公共 `urlHandler` 也不修改这里的 `view_url`。

**[4] `fields.view.loading_type`**：

| 值 | 描述 |
| --- | --- |
| `initial_load` | SDK 首次创建页面，或会话到期后在原页面重新开始记录。 |
| `route_change` | 应用内路由变化后创建页面。 |

`initial_load` 不一定表示浏览器重新下载了网页，也可能是用户停留很久后再次操作。该字段没有单独区分会话重建或 [BFCache（前进后退缓存）](https://web.dev/articles/bfcache) 恢复。

**[5] `fields.view.referer` 与 `fields.view.referrer`**：本版本使用了两种拼写。路由切换的上一页地址写在 `referer` 中，`referrer` 则可能仍为空字符串。

```text
搜索网站 → 打开订单列表 → 应用内切换到订单详情
             │                    │
bean.referer = 搜索来源        bean.referer 仍是搜索来源
                              view.referer = 订单列表地址
```

### c. Action（操作）

| 字段 | 类型 | 描述 | 说明 |
| --- | --- | --- | --- |
| `fields.action.id` *[1]* | str | 操作 ID | 把一次操作期间的接口、资源和错误关联起来。 |
| `fields.action.action_name` *[2]* | str | 操作名称 | 例如“查询订单”“提交订单”。 |
| `fields.action.action_type` *[3]* | str | 用户做了什么动作 | 默认记录点击事件 `click`。 |
| `fields.action.action_target_name` *[5]* | str | 实际触发事件的元素标签 | 例如 `button`、`a`、`input`，也可能是按钮内部的图标元素。 |
| `fields.action.timestamp` *[4]* | number | 操作开始时间 | 本机 Unix 毫秒时间戳。 |

**[1] `fields.action.id`**：一次点击可以引起请求、内容更新和图片加载。Aegis 会观察这些后续活动，让它们有机会关联到同一个操作，而不是点击一发生就立即结束 Action。

```text
点击“查询订单” → Action A 开始
                    │
                    ├── 接口请求中：继续等待
                    ├── DOM 或资源更新：重新等待页面安静下来
                    ├── 无待完成请求，连续 100 ms 无新活动 → A 结束
                    └── 达到 10 s 上限                    → A 结束
```

DOM 是浏览器中的页面元素树，文字变化、新增表格行等都属于 DOM 变化。观察期间已有 Action 时，新的点击不会再建立重叠 Action，因此该数据不等于原始点击次数。

**[2] `fields.action.action_name`**：优先使用元素或最近祖先上的 `data-aegis-action-name`，便于为图标按钮或复杂组件提供稳定、可读的名称。

```html
<button data-aegis-action-name="查询订单">查询</button>
```

没有自定义名称时，SDK 从被点击元素向上查找，在每个元素上按下表顺序寻找可读名称。找不到时再继续检查祖先元素，最后尝试普通文本。

| 优先级 | 名称来源 | 示例 |
| --- | --- | --- |
| `1` | 控件关联的 `label`，或按钮的值、文字。 | 输入框旁的“订单号”、按钮上的“查询”。 |
| `2` | `aria-label`，或 `aria-labelledby` 指向的文字。 | 没有可见文字的图标按钮，其无障碍名称为“关闭”。 |
| `3` | `alt`、`name`、`title`、`placeholder`，依次尝试。 | 图片的替代文字、输入框的提示文字。 |
| `4` | 选择控件的第一个选项文字。 | 下拉列表中的第一个选项。 |
| 最后 | 元素或祖先的普通文本。 | 链接中的“查看详情”。 |

名称会合并多余空白，超过约 `100` 个字符后截断并追加 ` [...]`。输入控件不会直接把用户输入的值作为名称，按钮类型的输入控件除外。

属性名可通过 `plugin.session.customActionNameAttribute` 修改。搜索名称时也会检查祖先元素，例如点击按钮内的图标，仍可能得到外层按钮的名称。

**[3] `fields.action.action_type`**：通过 `plugin.session.actionTypes` 指定要监听的 DOM 事件，下面列出默认值和可配置的常见例子。

| 值 | 描述 | 启用方式 |
| --- | --- | --- |
| `click` | 点击元素。 | 默认监听。 |
| `touchstart` | 手指开始接触屏幕。 | 加入 `actionTypes` 后监听。 |
| `keydown` | 按下键盘按键。 | 加入 `actionTypes` 后监听。 |
| `scroll` | 滚动页面或元素。 | 加入 `actionTypes` 后监听。 |

这不是封闭枚举，也可以配置其他 DOM 事件名。会话活跃检测本身监听这些动作，并不意味着默认会把它们全部记录为 Action。

**[4] `fields.action.timestamp`**：记录用户动作开始的本机时间，没有应用 `message.timestamp` 的服务器时钟校正。计算操作时长时，应使用相同时钟口径的时间。

对于 API，SDK 会估算请求开始时间；如果请求早于 Action 开始，该请求记录会移除 Action 关联，避免把先前发出的请求归到刚发生的点击上。

**[5] `fields.action.action_target_name`**：取浏览器事件目标的 `nodeName` 并转成小写。常见值如下，应用自定义元素也可能产生其他标签名。

| 值 | 描述 |
| --- | --- |
| `button` | 按钮。 |
| `a` | 链接。 |
| `input` | 输入框、复选框等输入控件。 |
| `select` | 下拉选择控件。 |
| `textarea` | 多行文本输入框。 |
| `span`、`div` | 文字或布局容器。 |
| `svg`、`path` | 矢量图标或图标中的路径。 |

点击“查询”按钮内部的图标时，操作名称可以来自按钮，目标标签却可能是 `path`。两者描述的是可读名称和实际触发位置，不要求对应同一个元素。

## 0x04 接口与静态资源

### a. API（接口请求）

```json
{
  "fields": { "type": "api", "level": "error", "plugin": "api" },
  "message": {
    "url": "https://example.com/api/orders",
    "method": "POST",
    "status": 200,
    "ret": "1001",
    "isErr": true,
    "requestType": "fetch",
    "duration": 125.5,
    "nextHopProtocol": "h2"
  }
}
```

示例省略公共时间、ID 和正文：HTTP 请求成功返回，但业务返回码 `1001` 表示失败。Aegis 同时监控 [Fetch](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API) 和 [XHR](https://developer.mozilla.org/en-US/docs/Web/API/XMLHttpRequest)，它们都是浏览器向服务端发请求的方式。

| 字段 | 类型 | 描述 | 说明 |
| --- | --- | --- | --- |
| `message.url` *[1]* | str | 接口地址 | 默认去掉 `?` 及后面的查询参数。 |
| `message.method` *[2]* | str | HTTP 请求方法 | 例如查询常用 `GET`，提交常用 `POST`。 |
| `message.status` *[3]* | number | HTTP 响应状态码 | 反映请求是否成功到达并获得响应。 |
| `message.ret` *[4]* | str 或 number | 业务返回码 | 从响应内容中提取，无法识别时为 `unknown`。 |
| `message.isErr` *[5]* | boolean | 业务返回码是否被判为错误 | 不包含全部网络和 HTTP 错误。 |
| `message.requestType` *[6]* | enum | 请求被识别为接口还是静态资源 | 普通 API 记录使用 `fetch`。 |
| `message.param` *[8]* | str | 请求体 | 例如提交的订单内容，需要开启 `apiDetail`。 |
| `message.data` *[8]* | str | 响应体 | 例如接口返回的 JSON 内容，需要开启 `apiDetail`。 |
| `message.reqHeaders` *[8]* | str | 选中的请求头 | 由 `plugin.api.reqHeaders` 指定要记录哪些头。 |
| `message.resHeaders` *[8]* | str | 选中的响应头 | 由 `plugin.api.resHeaders` 指定要记录哪些头。 |
| `message.trace` *[7]* | str | 后端调用链 ID | 从请求携带的链路追踪头中提取。 |
| `message.span` *[7]* | str | 请求携带的链路片段 ID | 与 `trace` 配合定位这次请求的链路上下文。 |

请求耗时和网络协议字段见本节的“请求耗时与协议”。详情字段未开启时通常为空字符串，网络失败等情况下还可能缺少响应相关字段。

**[1] `message.url`**：用于按接口查看请求数量、耗时和错误。例如 `/api/orders?page=1` 和 `/api/orders?page=2` 默认都记录为 `/api/orders`，路径中的订单 ID 则不会自动替换。

应用可以通过 `plugin.api.urlHandler(url, body)` 自定义聚合地址。该处理只改变 `url`，日志正文和错误摘要仍可能包含原始地址。

为限制同一接口反复上报，API 与静态资源共用按“项目 ID + URL”计数的限制。启用该限制时，默认保留前 `60` 条，首次丢弃超额记录后等待 `60 s` 清空项目计数，再允许记录。

是否启用限流，还取决于采样配置：使用数值型 `sample` 时，非零值可开启此判断；使用对象型配置时，要看其中的 `speed`，同时要求 `repeat>0`。随机采样和同地址限流分别执行，因此上报条数不一定等于实际请求次数。

**[2] `message.method`**：表示请求希望服务端执行的操作，常见 [HTTP 方法](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Methods) 如下。

| 值 | 描述 |
| --- | --- |
| `GET` | 获取数据。 |
| `POST` | 提交数据或执行操作。 |
| `PUT` | 完整替换资源。 |
| `PATCH` | 修改资源的部分内容。 |
| `DELETE` | 删除资源。 |
| `HEAD` | 仅获取响应头。 |
| `OPTIONS` | 查询允许的方法等通信选项。 |

SDK 保留传入的大小写，未显式指定时常记为 `get`。这是开放的字符串字段，上表不是 SDK 限定的封闭集合。

**[3] `message.status`**：来自浏览器的 HTTP 响应状态，常见值如下，其他值可查阅 [HTTP 状态码](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status)。

| 值 | 描述 |
| --- | --- |
| `0` | 没有获得可用 HTTP 响应，例如网络失败。 |
| `200` | 请求成功返回。 |
| `204` | 请求成功，响应没有正文。 |
| `304` | 资源未修改，可复用缓存内容。 |
| `400` | 服务端认为请求有误。 |
| `401` | 需要身份认证或认证未通过。 |
| `403` | 服务端拒绝访问。 |
| `404` | 请求的资源不存在。 |
| `429` | 请求过于频繁。 |
| `500` | 服务端内部错误。 |
| `502` | 网关收到无效的上游响应。 |
| `503` | 服务暂时不可用。 |
| `504` | 网关等待上游响应超时。 |

状态为 `0` 或 `>=400` 时，SDK 通常记录为 `ajax_error`。XHR 的网络错误、超时也属于这类错误；用户主动中止 XHR 默认不报告，设置 `plugin.api.reportAbort=true` 后才报告。

**[4] `message.ret`**：反映业务是否执行成功。例如 HTTP 返回 `200` 只代表收到正常响应，响应正文仍可以表示“库存不足”或“订单不存在”。

```json
{ "code": 1001, "message": "库存不足" }
```

默认提取顶层的 `ret`、`retcode`、`code` 或 `errcode`，忽略键名大小写；存在多个匹配键时，取响应对象中先出现的键。默认判断规则如下，业务错误码本身不是固定枚举。

| 提取结果 | 上报的 `ret` | 默认判断 |
| --- | --- | --- |
| `0` 或 `"0"` | `"0"` | 未发现业务错误。 |
| 空字符串、`"未知"`、没有匹配键或无法解析 JSON | `"unknown"` | 没有识别到业务结果。 |
| `"unknown"` | `"unknown"` | 没有识别到业务结果。 |
| 其他值，例如 `1001` | 对应字符串，例如 `"1001"` | 业务错误。 |

使用不同成功码的应用可以通过 `retCodeHandler` 返回 `{ code, isErr }`，直接指定业务返回码和判断结果。XHR 还支持 `retCodeHandlerAsync`，Fetch 使用同步处理器。

**[5] `message.isErr`**：只说明业务返回码判断结果，需与 HTTP 状态和日志级别一起阅读。

| 值 | 描述 |
| --- | --- |
| `true` | 业务结果被判为错误。 |
| `false` | 未判出业务错误，也包括未能识别业务返回码。 |
| 不携带 | 此记录没有业务判断结果，例如 Fetch 请求直接失败。 |

```text
网络或 HTTP 失败                  → level=ajax_error
HTTP 正常返回，业务码表示失败      → level=error，isErr=true
HTTP 正常返回，未判出业务错误      → level=info，isErr=false
```

**[6] `message.requestType`**：SDK 根据 URL 后缀、响应内容类型或 `resourceTypeHandler` 区分两类请求。

| 值 | 描述 |
| --- | --- |
| `fetch` | 接口类请求，同时包含 Fetch 和 XHR。 |
| `static` | 被识别为脚本、图片等静态资源的请求。 |

静态请求会以 `fields.type=assets_speed` 上报，此时不保证保留 `requestType`。因此 `fetch` 不能用来判断“这次请求使用了 Fetch 而不是 XHR”。

**[7] `message.trace` 与 `message.span`**：用于从浏览器请求找到服务端处理过程。[Trace Context（调用链上下文）](https://www.w3.org/TR/trace-context/) 通过请求头传递标识，使不同服务能够关联同一次调用。

```text
用户点击提交订单
    ↓
浏览器请求携带 traceparent
    ├── Aegis 提取 trace、span，记入接口日志
    └── 后端接收同一请求头，继续记录调用链
```

| 请求头 | Trace ID 的读取方式 | Span ID 的读取方式 |
| --- | --- | --- |
| `traceparent` | 按 `-` 分段后的第 `2` 段。 | 第 `3` 段。 |
| `b3` | 第 `1` 段。 | 第 `2` 段。 |
| `sentry-trace` | 第 `1` 段。 | 第 `2` 段。 |
| `sw8` | 第 `2` 段做 Base64 解码。 | 第 `3` 段做 Base64 解码。 |

`plugin.api.injectTraceHeader` 用于开启主动注入，已有请求头也可被读取。以 `traceparent` 为例，SDK 为请求生成新的 Trace ID 和 Span ID，不使用 Session ID 代替。

未读取到追踪头时，两字段通常为空字符串。`injectTraceUrls` 可限制注入范围，空数组表示不注入，`injectTraceIgnoreUrls` 用于排除地址。

**[8] `message.param`、`message.data` 与请求头**：请求体和响应体以文本保存，可分别通过 `reqParamHandler`、`resBodyHandler` 处理，最多保留 `102,400` 个字符。

请求头与响应头只保存配置选中的名称，以多行文本表示，例如 `req header x-request-id: abc`。请求头采集与 `apiDetail` 开关独立。

### b. Resource（静态资源）

| 字段 | 类型 | 描述 | 说明 |
| --- | --- | --- | --- |
| `message.url` | str | 资源地址 | 例如图片或脚本 URL，自动资源采集会去掉查询部分。 |
| `message.urlQuery` | str | 资源地址中的查询参数 | 例如 `v=2`，不含开头的 `?`。 |
| `message.assetType` *[1]* | str | 资源类型 | 例如 `js`、`css`、`img`。 |
| `message.status` *[2]* | number | 加载结果 | `assetSpeed` 插件用固定值表示成功和失败。 |
| `message.transferSize` *[3]* | number | 网络传输大小（bytes） | 仅保留浏览器返回的正数，否则记为 `-1`。 |
| `message.isHttps` *[4]* | boolean | 是否通过 HTTPS 加载 | 相对地址使用当前页面的协议判断。 |
| `message.method` *[6]* | str | 请求方法 | `assetSpeed` 插件使用固定值。 |
| `message.msg` *[5]* | str | 资源记录说明 | 标记自动资源采集的成功或失败结果。 |

`assetSpeed` 插件采集页面中的脚本、样式、图片和媒体加载，`api` 插件也可能产生资源记录。后者可能没有 `assetType` 或 `method`，应结合 `fields.plugin` 判断来源。

**[1] `message.assetType`**：表示资源的加载类别，默认值如下，也可通过 `plugin.api.resourceTypeHandler` 自定义。

| 值 | 描述 |
| --- | --- |
| `js` | 通过脚本元素加载的 JavaScript。 |
| `css` | 样式相关资源，包括 Link 加载和 CSS 规则触发的资源。 |
| `img` | 图片元素加载的资源。 |
| `audio` | 音频资源。 |
| `video` | 视频资源。 |
| `static` | 没有识别出更具体类别的静态资源。 |

**[2] `message.status`**：自动资源采集能观察到“加载完成”或“加载失败”，但并不总能获得真实 HTTP 状态码。

| 来源 | 值 | 描述 |
| --- | --- | --- |
| `assetSpeed` | `200` | 记录来自资源加载完成的性能条目。 |
| `assetSpeed` | `400` | 捕获到资源加载错误。 |
| `api` | 浏览器返回的 HTTP 状态码 | 请求被归类为静态资源。 |
| `api` 的 Fetch 失败记录 | `400` | 请求失败时使用的替代值。 |

例如图片实际返回 `404`，`assetSpeed` 仍可能报告 `400`。同一次失败还可能产生一条 `image_error` 日志，分别描述资源结果和错误详情。

**[3] `message.transferSize`**：用于了解资源经网络传输了多少数据。浏览器的 [`transferSize`](https://developer.mozilla.org/en-US/docs/Web/API/PerformanceResourceTiming/transferSize) 包含响应头开销和传输中的正文大小，不等于图片解码或脚本解压后的大小。

| 浏览器提供的数据 | Aegis 上报值 | 如何理解 |
| --- | --- | --- |
| 大于 `0` | 保留原值 | 有可见的传输大小。 |
| 等于 `0` | `-1` | 可能命中本地缓存，也可能受跨域信息限制。 |
| 没有可用大小 | `-1` 或不携带字段 | 无法从该记录获得传输大小。 |

```text
浏览器直接使用本地缓存 → transferSize 可能为 0 → Aegis 写 -1
浏览器隐藏跨域资源信息 → transferSize 也可能为 0 → Aegis 写 -1
```

因此 `-1` 表示没有可用的正数大小，不能直接判定缓存命中。浏览器重新向服务器验证缓存时也可能有传输开销，[Resource Timing](https://www.w3.org/TR/resource-timing/#dom-performanceresourcetiming-transfersize) 将验证后复用缓存的大小定义为 `300 bytes`。

**[4] `message.isHttps`**：

| 值 | 描述 |
| --- | --- |
| `true` | 地址使用 HTTPS，或相对地址所在页面使用 HTTPS。 |
| `false` | 未识别为 HTTPS。 |

**[5] `message.msg`**：资源记录中的固定文本还取决于采集插件。

| 值 | 描述 |
| --- | --- |
| `asset_speed` | 已采集到资源加载完成的性能条目。 |
| `static_fail` | 捕获到资源加载失败。 |
| `api` | `api` 插件将请求识别为静态资源，沿用请求计时记录的标记。 |

前两个值来自 `assetSpeed` 插件；`api` 插件的失败记录也可能使用其他错误文本，不能只根据 `msg` 判断资源是否加载成功。

**[6] `message.method`**：`assetSpeed` 观察浏览器加载资源后的结果，不读取发起请求时的方法，统一填写以下值。

| 值 | 描述 |
| --- | --- |
| `get` | 自动资源采集使用的方法标记。 |

`api` 插件归类出的资源记录可能没有此字段，不能仅凭资源记录补出所有请求的真实方法。

### c. 请求耗时与协议

```text
查找服务器地址 → 建立连接 → 发出请求 → 收到首字节 → 收完响应
    DNS          TCP/TLS      等待响应       下载正文
```

[Resource Timing（资源计时）](https://www.w3.org/TR/resource-timing/) 是浏览器记录请求各阶段时间的能力。图中的 TLS 是建立 HTTPS 安全连接时的握手过程，连接复用时则可能跳过重新建连。

Aegis 使用以下时间差计算耗时，单位均为 `ms`，保留 `2` 位小数。

| 字段                              | 类型     | 描述                    | 计算来源                                    |
| ------------------------------- | ------ | --------------------- | --------------------------------------- |
| `message.duration` *[1]*        | number | 本次请求的总耗时              | 浏览器提供的 `duration`，缺失时由 SDK 计时。          |
| `message.domainLookup`          | number | DNS 查询耗时，即查找服务器地址所用时间 | `domainLookupEnd - domainLookupStart`。  |
| `message.connectTime`           | number | 建立连接的耗时，可能包含 TLS 握手   | `connectEnd - connectStart`。            |
| `message.tlsTime` *[2]*         | number | 从开始建立安全连接到发出请求的耗时     | `requestStart - secureConnectionStart`。 |
| `message.tcpAndRequestGap`      | number | 连接就绪后，等待开始发送请求的时间     | `requestStart - connectEnd`。            |
| `message.requestTime`           | number | 请求发出后，等待首字节响应的时间      | `responseStart - requestStart`。         |
| `message.responseTime` *[2]*    | number | 接收响应正文的耗时             | `responseEnd - responseStart`。          |
| `message.preHandleTime` *[2]*   | number | 资源获取起点与 DNS 起点的时间差    | `fetchStart - domainLookupStart`，可能为负。  |
| `message.nextHopProtocol` *[3]* | str    | 浏览器与下一跳通信所用的协议        | 例如浏览器连接 CDN 时使用的 HTTP 版本。               |

**[1] `message.duration`**：优先使用浏览器测量的请求耗时。没有匹配的性能条目时，API 使用 SDK 记录的请求起止时间差，其他阶段耗时写 `-1`，表示该阶段没有可用数据。

| 场景 | 数据表现 |
| --- | --- |
| 找到对应的资源计时条目 | 使用浏览器的总耗时和阶段时间差。 |
| API 没有对应计时条目 | 总耗时使用 SDK 计时，阶段耗时为 `-1`。 |
| 静态资源加载失败且没有计时条目 | 总耗时可以为 `0`，阶段耗时为 `-1`。 |

SDK 按 URL 取最后一条资源计时记录；同一 URL 同时请求多次时，匹配到的耗时可能属于另一请求。

各字段回答的问题也不同。例如 `requestTime` 偏大，表示发出请求后迟迟没有开始收到响应，可能涉及网络往返或服务端处理；`responseTime` 偏大，则表示收到首字节后还花了较长时间接收剩余内容。

连接和安全握手有重叠，不能把表中所有字段直接相加。假设一次请求的时间点如下，数值均为相对页面计时起点的毫秒数：

```text
100 开始连接 → 120 开始 TLS → 160 连接就绪 → 170 发出请求

connectTime      = 160 - 100 = 60 ms
tlsTime          = 170 - 120 = 50 ms
tcpAndRequestGap = 170 - 160 = 10 ms
```

这里的 `tlsTime=50` 同时覆盖安全握手和连接就绪后的等待，不能把它完整算作独立的握手阶段。

**[2] `message.tlsTime`、`message.responseTime` 与 `message.preHandleTime`**：浏览器缺少部分时间点时，以下取值需要特别区分。

| 字段 | 特殊条件 | 实际结果 |
| --- | --- | --- |
| `tlsTime` | `secureConnectionStart=0` | 仍执行减法，所以非零结果不一定是实际 TLS 耗时。 |
| `responseTime` | `responseStart=0` | 改用总耗时，不再仅表示正文下载。 |
| `preHandleTime` | `domainLookupStart=0` | 写 `0`。 |
| `preHandleTime` | DNS 起点晚于资源获取起点 | 按既定减法得到负数。 |

例如资源获取从 `100 ms` 开始、DNS 从 `104 ms` 开始，`preHandleTime` 会写成 `100-104=-4 ms`。负值来自减法方向，不表示请求“倒退了四毫秒”；它不能直接当作正向的请求准备耗时。

跨域资源没有开放详细计时时，浏览器可能将 DNS、连接等时间点隐藏为 `0`。因此，阶段耗时为 `0` 既可能表示复用了连接、没有经历该阶段，也可能表示浏览器未提供细节，具体限制见 [Resource Timing](https://developer.mozilla.org/en-US/docs/Web/API/PerformanceResourceTiming)。

**[3] `message.nextHopProtocol`**：来自浏览器的 [`nextHopProtocol`](https://developer.mozilla.org/en-US/docs/Web/API/PerformanceResourceTiming/nextHopProtocol)，常见值如下。

| 值 | 描述 |
| --- | --- |
| `http/1.1` | HTTP/1.1。 |
| `h2` | HTTP/2。 |
| `h3` | HTTP/3。 |
| 空字符串 | 没有取得协议信息。 |

SDK 保留浏览器返回的协议名称，因此还可能出现其他值。它描述浏览器到下一跳的连接，不代表服务端内部各服务之间也使用相同协议。

## 0x05 页面性能

### a. 页面加载与首屏

| 字段 | 类型 | 描述 | 说明 |
| --- | --- | --- | --- |
| `message.dnsLookup` | number | DNS 查询耗时（ms） | 查找页面服务器地址所用时间。 |
| `message.tcp` | number | 建立连接耗时（ms） | HTTPS 连接时也包含安全握手时间。 |
| `message.ssl` | number | HTTPS 安全握手到请求开始的耗时（ms） | 没有安全连接起点时为 `0`。 |
| `message.ttfb` *[1]* | number | 请求发出后等待首字节的时间（ms） | 反映网络往返与服务端响应等待。 |
| `message.contentDownload` | number | 下载 HTML 响应的耗时（ms） | 从收到首字节到收完响应。 |
| `message.domParse` *[4]* | number | HTML 开始解析到文档解析完成的耗时（ms） | `domInteractive - domLoading`。 |
| `message.resourceDownload` *[4]* | number | 文档解析完成到页面开始触发 load 的时间（ms） | `loadEventStart - domInteractive`。 |
| `message.firstScreenTiming` *[2]* | number | 首屏主要内容出现的估算时间（ms） | 基于页面元素变化，最终向下取整。 |
| `message.engineInit` *[5]* | number | 应用提供的引擎初始化耗时（ms） | 可选，由 `extraPerformanceData.engineInit` 提供。 |
| `message.bundleLoad` *[5]* | number | 应用提供的代码包加载耗时（ms） | 可选，由 `extraPerformanceData.bundleLoad` 提供。 |

这些记录使用 `fields.type=page_performance`。导航阶段时间取自浏览器的 [`performance.timing`](https://developer.mozilla.org/en-US/docs/Web/API/PerformanceTiming)，用于描述文档加载；单页应用切换路由不会重新计算同一套文档加载指标。

**[1] `message.ttfb`**：首字节等待表示“请求发出后，多久开始收到响应”。此字段从 `requestStart` 算到 `responseStart`，不包含此前的 DNS 查询和连接建立时间。

```text
开始导航 ─ DNS ─ 建立连接 ─ 发出请求 ─ 等待服务端 ─ 收到首字节
                              └──── Aegis ttfb ────┘
```

**[2] `message.firstScreenTiming`**：首屏是用户不滚动页面就能看到的区域。Aegis 通过 [MutationObserver（页面元素变化观察器）](https://developer.mozilla.org/en-US/docs/Web/API/MutationObserver) 观察新增内容，估算首屏主体何时出现。

| 页面情况 | 取值方式 |
| --- | --- |
| 新增了 `AEGIS-FIRST-SCREEN-TIMING` 标记元素 | 优先使用标记元素出现的时间，多次标记取最后一次。 |
| 首次内容绘制时已有标记元素 | 可以直接使用该次 FCP 时间。 |
| 没有标记元素 | 从首屏可见的新增内容中，选择包含元素最多的子树出现时间。 |

这里的标记是元素上的 HTML 属性。例如订单列表已经准备好时，可以把带有以下属性的主体元素加入页面：

```html
<main AEGIS-FIRST-SCREEN-TIMING>订单列表内容</main>
```

`AEGIS-IGNORE-FIRST-SCREEN-TIMING` 属性可排除不应参与判断的区域。这个指标依据元素出现推测首屏完成，不代表所有图片下载结束，也不代表所有接口都已返回。

```text
页面开始加载
    ├── 出现导航栏
    ├── 出现占位内容
    └── 出现订单列表主体 ← 标记或 DOM 变化判断的首屏时刻
            └── 部分图片仍可能继续下载
```

未通过 FCP 标记提前确定结果时，SDK 先等待 `3 s` 收集页面变化；必要时间仍未产生时，再延后计算。字段保存的是页面计时起点到选中内容出现的时间，等待计算和合批发送不会直接加到这个值上。

**[3] 耗时取值范围**：为处理异常时间，SDK 对本节指标设置了范围，超范围时使用固定替代值。

| 字段                                               | 接受范围          | 超范围或无效时的取值   |
| ------------------------------------------------ | ------------- | ------------ |
| `dnsLookup`、`tcp`、`ssl`、`ttfb`、`contentDownload` | `0～15,000 ms` | `0`。         |
| `domParse`、`resourceDownload`                    | `0～15,000 ms` | `1,070 ms`。  |
| `firstScreenTiming`                              | `0～15,000 ms` | `15,000 ms`。 |
| `engineInit`、`bundleLoad`                        | `0～10,000 ms` | `0`。         |

例如 `firstScreenTiming=15,000` 既可能是测得的值，也可能是替代值。查看极端耗时时，应结合其他加载指标判断。

**[4] `message.domParse` 与 `message.resourceDownload`**：浏览器边接收 HTML 边解析文档，因此 `domParse` 可以与 HTML 下载重叠。`domInteractive` 表示文档已解析完成，不保证业务按钮已绑定事件或接口数据已加载。

```text
开始解析 HTML ── domParse ── 文档解析完成 ── resourceDownload ── 开始触发 load
```

`resourceDownload` 包含这个区间内剩余资源加载、脚本执行等等待，不能理解为所有资源下载耗时之和。单个接口或图片慢在哪里，应查看对应的 API 或 Resource 记录。

**[5] `message.engineInit` 与 `message.bundleLoad`**：SDK 不自动识别业务引擎或代码包的起止点，而是读取应用通过 `extraPerformanceData` 提供的结果。接入方需要先完成计时并提供毫秒值；这两个字段随页面性能记录一起发送。

### b. Web Vitals（用户体验指标）

```json
{
  "FCP": 800,
  "LCP": 1200,
  "FID": 8,
  "CLS": 0.06,
  "INP": 96
}
```

SDK 分别计算这五个指标并暂存在内存中，在页面首次隐藏或离开时，将它们合成一条 `type=web_vitals` 记录。上述字段都位于这条记录的 `message` 中，不逐个发送，也不按 Session 累加。

| 字段                  | 类型     | 描述                                                                     | 单位  |
| ------------------- | ------ | ---------------------------------------------------------------------- | --- |
| `message.FCP` *[1]* | number | [首次内容绘制](https://web.dev/articles/fcp)：页面第一次显示文字、图片等内容的时间。             | ms  |
| `message.LCP` *[1]* | number | [最大内容绘制](https://web.dev/articles/lcp)：可见区域内最大的文字块或图片等内容完成绘制的时间。       | ms  |
| `message.FID` *[2]* | number | [首次输入延迟](https://web.dev/articles/fid)：用户第一次交互后，浏览器等待多久才开始处理。          | ms  |
| `message.INP` *[2]* | number | [交互到下一次绘制](https://web.dev/articles/inp)：从交互开始到页面给出下一帧反馈的延迟，代表较慢的一次交互。 | ms  |
| `message.CLS` *[3]* | number | [累积布局偏移](https://web.dev/articles/cls)：页面内容意外移动的程度，例如图片加载后把按钮挤到别处。     | 无量纲 |

**[1] `message.FCP` 与 `message.LCP`**：FCP 记录第一次出现内容的耗时，测得后保存。LCP 随页面加载更新最大内容候选，记录最后确认的候选耗时；只显示加载提示就可能产生 FCP，主体图片稍后出现才成为 LCP 候选。

```text
0 ms 开始加载 → 800 ms 出现标题 → 1,200 ms 出现大图
                    FCP                 LCP 候选
```

Aegis 在首次点击、按键或页面隐藏等时机结束这次 LCP 观察，保存结果供统一上报，不对多个候选求平均。上报只保留耗时，不包含具体元素信息。

**[2] `message.FID` 与 `message.INP`**：FID 只保存第一次有效输入的等待时间，后续交互不改变它。INP 比较多次交互的响应速度，还覆盖事件处理和下一帧展示。

```text
点击 → 等待主线程空闲 → 执行事件处理 → 绘制反馈
       └─ 输入延迟 ─┘
       └──────── 一次交互的 INP 延迟 ────────┘
```

浏览器正在执行耗时脚本时，点击需要先排队，这会增加输入延迟。事件处理或绘制很慢，则会继续增加整次交互的延迟。

SDK 按交互 ID 合并同一次交互的事件，以其中最大的事件耗时作为该次延迟，并保留最慢的 `10` 次交互。随后根据交互总数选择结果：

| 已发生的交互数 | 从慢到快选择的位置 |
| --- | --- |
| `1～49` | 最慢的第 `1` 次。 |
| `50～99` | 第 `2` 次，忽略最慢的 `1` 次。 |
| `100～149` | 第 `3` 次，忽略最慢的 `2` 次。 |
| 更多 | 每增加 `50` 次向后选一位，最多取保留列表中的第 `10` 次。 |

例如三次交互分别为 `80 ms`、`240 ms`、`100 ms`，INP 取 `240 ms`，不是平均值 `140 ms`。选值依赖浏览器实际提供的事件，缺少足够候选时取已有列表的末项。

**[3] `message.CLS`**：数值越大，表示页面内容移动越明显。SDK 将间隔小于 `1 s`、总跨度小于 `5 s` 的布局变化合成一段，取累计偏移最大的那一段，而不是把整次访问的所有变化简单相加。

例如两段变化各累计 `0.08`、`0.12`，最终取 `0.12`，不相加为 `0.20`。

由近期用户输入触发、被浏览器标记为预期内的布局变化不计入。这有助于区分“用户展开面板”和“广告突然加载，把正在点击的按钮推走”。

**[4] 指标的 `-1`**：五个指标都从 `-1` 开始，表示尚未保存有效测量结果。本版本仅保存大于 `0` 的结果，合法零值也会保留为 `-1`。

| 测量情况 | 上报结果 | 解释 |
| --- | --- | --- |
| 获得正数结果 | 该数值 | 可作为测量结果使用。 |
| 未发生可测量交互或浏览器不支持 | 可能为 `-1` | 没有取得对应指标。 |
| 实际测量为 `0`，例如没有布局偏移 | 仍为 `-1` | 此版本没有保留零值。 |

因此 `CLS=-1` 既可能是未测得，也可能是实际为零，统计时不应当作负的偏移分数。

**[5] 汇聚与上报时机**：五个指标共用一次上报机会，由首次页面隐藏或 `pagehide`（页面离开）触发。切到其他标签页也算隐藏，不必等到关闭页面。

```text
页面加载、交互和布局变化 → 分别计算并保存指标
    ↓ 首次隐藏或离开
安排 10 ms 后读取五个结果 → 合成一条 web_vitals 记录
    ↓
进入公共合批、采样和网络发送流程
```

`10 ms` 是生成记录前的等待时间，不代表请求已发出或服务端已收到。五个指标共用一个事件 ID 和时间戳，时间戳表示生成记录的时刻，不是各指标发生的时刻。

| 后续行为 | 是否再次上报 |
| --- | --- |
| 切回页面继续操作，再次切走 | 不会，首次触发后已移除上报监听。 |
| SPA 内部切换路由 | 不会因此重新采集或发送一套指标。 |
| 刷新页面、重新加载并初始化 SDK | 重新开始采集，等待新页面首次隐藏或离开。 |

指标按网页文档采集，关联信息却取生成记录时的当前页面。如果用户先从订单列表切到详情页、再隐藏页面，初始加载的 FCP、LCP 可能携带详情页的 View ID，不能据此解释为详情页的路由加载耗时。

## 0x06 错误与白屏

### a. Error（错误）

| 字段 | 类型 | 描述 | 说明 |
| --- | --- | --- | --- |
| `message.errorMsg` *[1]* | str | 错误摘要 | 便于在列表中查看，例如 `TypeError: ...`。 |
| `message.msg` *[2]* | str | 错误详细内容 | 可以包含脚本位置、调用堆栈或资源地址。 |

**[1] `message.errorMsg`**：摘要用于快速识别错误，具体内容取决于来源。

| 错误来源 | 摘要内容 |
| --- | --- |
| JavaScript 执行错误 | 浏览器提供的错误消息。 |
| 未处理的 Promise 失败 | 优先取失败原因中的 `message` 或 `errMsg`，最多 `150` 个字符。 |
| 接口错误 | 通常由接口 URL 和业务返回码组成。 |
| 资源加载失败 | 可以不提供单独摘要，详情保存在 `msg`。 |

Promise 是 JavaScript 表达异步任务结果的对象。异步任务失败且应用没有处理该失败时，SDK 会记录 `promise_error`，帮助发现被遗漏的异步异常。

**[2] `message.msg`**：用于查看错误发生的位置和上下文。JavaScript 执行错误的正文通常包含“错误消息 + 脚本 URL + 行列号 + 堆栈”，堆栈描述函数如何逐层调用到出错位置。

资源错误则可能是 `img load fail: https://example.com/logo.png` 这样的文本。文件名、行列号和堆栈没有统一拆成独立字段，需要结合具体正文格式读取。

### b. Blank Screen（白屏）

| 字段 | 类型 | 描述 | 说明 |
| --- | --- | --- | --- |
| `message.triggerTime` *[1]* | number | 页面开始后多久触发这次检测（ms） | 已扣除配置的防抖等待时间。 |
| `message.whitePointCount` *[2]* | number | 检测点中落在空容器上的数量 | 数值越多，表示更多位置没有看到业务内容。 |
| `message.samePointerMap` *[3]* | object | 每种元素组合在检测点中出现的次数 | 按检测点上元素从前到后的叠放顺序组合。 |
| `message.maximumSamePointer` *[3]* | object | 出现次数最多的元素组合及其次数 | 只保存出现最多的一项。 |
| `message.linkLogId` *[4]* | str | 检测附近的错误日志 ID | 有关联错误时提供。 |
| `message.linkLogType` *[5]* | str | 关联错误日志的数据类型 | 复制原日志的 `type`。 |
| `message.linkLogLevel` *[5]* | str | 关联错误日志的错误类别 | 复制原日志的 `level`。 |
| `message.linkErrorMsg` | str | 关联错误的摘要 | 复制原日志的 `errorMsg`。 |
| `message.msg` *[6]* | enum | 白屏明细标记 | 与用于计数的 PV 记录区分。 |

白屏明细使用 `fields.type=normal, fields.level=blank_screen`。SDK 根据页面结构判断疑似白屏，不通过截图识别屏幕颜色。

**[1] `message.triggerTime`**：帮助判断白屏出现在刚打开页面，还是使用一段时间之后。它不表示白屏持续了多久。

```text
页面计时起点 → 出现错误或内容变化 → 防抖等待 → 执行检测
               └─ triggerTime 接近这一位置
```

初始计时起点取页面的性能时间原点，SPA 插件识别到新页面访问后会重设起点。计算结果小于 `0` 时记为 `0`。

**[2] `message.whitePointCount`**：SDK 在视口横线、竖线和两条对角线上选点，通过 [`elementsFromPoint()`](https://developer.mozilla.org/en-US/docs/Web/API/Document/elementsFromPoint) 读取每个位置从前到后叠放的元素。最上层元素命中 `containers`，且未命中 `ignoreContainers` 时，该点计为空白点。

默认容器包括 `body`、`html`、`#app`、`#root`。SDK 将元素转换成带标签名的标识后进行完整字符串匹配，例如 `id=app` 的 `div` 会变成 `div#app`；若希望匹配这个元素，配置中也要使用 `div#app`，只写 `#app` 不等同于 CSS 选择器查询。

```text
页面发生错误或内容变化
    ↓ 等待默认 1,500 ms，避免把短暂加载当白屏
第一次检查：空白点或相同容器过多
    ↓ 再等待默认 1,500 ms
第二次仍命中 → 上报白屏明细
第二次恢复   → 不上报本次疑似白屏
```

默认两种阈值配置均为 `70%`，SDK 使用 `floor((4 × everySideSampleNumber - 3) × 70%)` 换算计数阈值。默认 `everySideSampleNumber=9` 时，阈值为 `23`，空白点达到此数或相同元素组合达到其阈值，都可能触发复检。

这里的百分比用于计算阈值，SDK 没有在记录中提供实际采样总数，不能直接把 `whitePointCount=23` 换算成“屏幕有 `70%` 空白”。第二次检查用于确认是否仍然白屏，上报的计数和元素组合保留第一次检查的结果。

**[3] `message.samePointerMap` 与 `message.maximumSamePointer`**：SDK 取每个检测点最前面的至多 `5` 个元素标识，用 ` < ` 连接后计数。标识优先使用“标签名 + ID”，没有 ID 时使用类名，例如 `div#app` 或 `main.content`。

```json
{
  "samePointerMap": {
    "div#app < body < html": 25,
    "main.content < div#app < body < html": 12
  },
  "maximumSamePointer": {
    "div#app < body < html": 25
  }
}
```

示例中，`25` 个检测点返回了相同组合，`maximumSamePointer` 保存其中次数最多的一项。` < ` 表示这些元素的叠放顺序，不保证它们逐层构成 DOM 父子关系，例如浮层也可能挡在内容前面。

大量检测点返回相同组合，可能表示页面停留在空容器或大面积遮罩上。最高频组合以 `canvas`、`img`、`svg`、`iframe` 开头时，SDK 排除“相同元素过多”这一判断，因为这些单个元素本身就可能承载大块业务内容。

**[4] `message.linkLogId`**：关联最近捕获的非白屏错误，便于从白屏跳转到错误详情。例如脚本执行失败后出现白屏，可以沿此 ID 查找那条错误的堆栈。

这是时间上的关联线索，不代表已经证明因果关系。白屏插件还会产生 `type=pv, level=blank_screen` 的计数记录，计数记录与白屏明细应分开使用。

**[5] `message.linkLogType` 与 `message.linkLogLevel`**：描述被关联的错误，不是白屏记录自身的分类。自动采集的关联日志常见以下类型：

| `linkLogType` 值 | 描述 |
| --- | --- |
| `normal` | JavaScript、异步任务或资源加载错误。 |
| `api` | 接口请求错误。 |
| `websocket` | WebSocket 插件报告的连接错误。 |

| `linkLogLevel` 值 | 描述 |
| --- | --- |
| `error` | JavaScript 执行或接口业务错误。 |
| `promise_error` | 未处理的异步任务失败。 |
| `ajax_error` | 接口网络或 HTTP 错误。 |
| `script_error` | 脚本加载失败。 |
| `css_error` | 样式加载失败。 |
| `image_error` | 图片加载失败。 |
| `media_error` | 媒体加载失败。 |
| `websocket_error` | WebSocket 错误。 |

如果应用通过采集回调修改了原始日志，上述字段也随原日志变化。

**[6] `message.msg`**：白屏明细只使用以下固定值；`type=pv, level=blank_screen` 的计数记录可以不携带本字段。

| 值 | 描述 |
| --- | --- |
| `blank_screen` | 两次检测均命中白屏条件后发送的明细记录。 |

## 0x07 自定义事件与 WebSocket

### a. 自定义上报

| API | 用途 | `fields.type` | `fields.level` |
| --- | --- | --- | --- |
| `info(...)` | 记录业务日志。 | `normal` | `info` |
| `error(...)` | 主动记录业务错误。 | `normal` | `custom_error` |
| `report(...)` | 按应用指定的分类上报。 | 调用者提供，缺省为 `normal`。 | 调用者提供，缺省为 `info`。 |
| `reportEvent(...)` | 记录业务事件。 | `custom_event` | `info` |
| `reportTime(...)` | 上报已有的耗时结果。 | `custom_time` | `info` |
| `time(name)` → `timeEnd(name)` | 由 SDK 记录两次调用之间的耗时。 | `custom_time` | `info` |

| 字段 | 类型 | 描述 | 说明 |
| --- | --- | --- | --- |
| `message.name` *[1]* | str | 业务事件或计时名称 | 例如 `order_submit_success`、`report_export`。 |
| `message.duration` *[2]* | number | 自定义操作耗时（ms） | 仅计时记录提供。 |
| `message.msg` *[3]* | any | 业务日志正文或事件说明 | SDK 可填入固定标记，也允许业务提供内容。 |
| `message.<业务字段>` | any | 此事件携带的业务信息 | 例如 `orderId`、`result`。 |

**[1] `message.name`**：用稳定名称表示“发生了哪类事情”，把订单号等每次变化的信息放到独立字段，便于按名称统计事件次数。

```javascript
aegis.reportEvent({
  name: 'order_submit_success',
  orderId: 'order-123',
});
```

这条记录的名称是 `order_submit_success`，订单号另存为 `message.orderId`。扩展字段应避开 SDK 已有字段名，事件 ID 和时间仍由 SDK 填写。

**[2] `message.duration`**：业务已经计算好耗时时使用 `reportTime()`，希望 SDK 帮忙计时时使用同名的 `time()` 和 `timeEnd()`。

```javascript
aegis.reportTime('report_export', 1250);

aegis.time('report_export');
// 执行导出任务。
aegis.timeEnd('report_export');
```

`reportTime()` 接受 `0～60,000 ms`，超范围不报告。`timeEnd()` 直接计算两次调用的时间差，没有相同的范围检查，因此自定义耗时记录仍可能超过 `60 s`。

同名计时在结束前不能重复启动；重复调用 `time(name)` 会保留原起点，未启动就调用 `timeEnd(name)` 则不产生记录。一次计时结束后会删除起点，后续可用同一名称开始下一次计时。

**[3] `message.msg`**：以下是 SDK 自动填入的标记，业务正文没有固定枚举。

| 值 | 使用场景 |
| --- | --- |
| `report_event` | 用字符串调用 `reportEvent('order_submit_success')`。 |
| `custom_time` | `reportTime()` 或 `timeEnd()` 产生的计时记录，且业务未覆盖此字段。 |
| 业务提供的值 | `info()`、`error()`、`report()` 的正文，或对象形式事件中提供的 `msg`。 |
| 空字符串 | 对象形式的 `reportEvent()` 未提供 `msg` 时，使用空字符串，不会自动补上 `report_event`。 |

### b. WebSocket（长连接）

[WebSocket](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket) 让浏览器和服务端保持连接并双向发送消息，常用于聊天、通知和实时数据。Aegis 记录连接是否建立成功、建立耗时及连接相关错误。

| 字段 | 类型 | 描述 | 说明 |
| --- | --- | --- | --- |
| `message.url` | str | WebSocket 地址 | 例如 `wss://example.com/notifications`。 |
| `message.successFlag` *[1]* | boolean | 这次是否成功建立连接 | 建连结果记录提供。 |
| `message.duration` | number | 建立连接所用时间（ms） | 从创建 WebSocket 到收到 `open`，成功时提供。 |
| `message.retryFlag` *[2]* | boolean | 同一地址前一次连接尝试是否失败 | 用于区分首次连接和失败后的再次尝试。 |
| `message.msg` *[3]* | str | 连接结果或错误说明 | 例如连接成功、连接失败或发送错误。 |

**[1] `message.successFlag`**：

| 值 | 描述 |
| --- | --- |
| `true` | 收到 `open` 事件，连接已建立。 |
| `false` | 尚未收到 `open` 就发生 `close`，且关闭码不是正常关闭码 `1000`。 |

这个字段只描述建连结果：成功记录的 `duration` 是创建连接到收到 `open` 的时间，不是连接保持了多久。已建立的连接即使之后异常断开，也不会因此补发 `successFlag=false` 的建连记录。

独立的 WebSocket 错误日志使用 `level=websocket_error`，不一定携带 `successFlag`。建连失败记录本身仍为 `level=info`，统计建连成功率应读取此布尔值。

**[2] `message.retryFlag`**：

| 值 | 描述 |
| --- | --- |
| `false` | 此地址没有保留的前次建连失败标记。 |
| `true` | 此地址前一次建连尝试失败，本次再次尝试。 |

```text
第一次连接失败 → successFlag=false，retryFlag=false
第二次连接成功 → successFlag=true， retryFlag=true
后续重新连接   → 前次失败标记已清除，retryFlag=false
```

SDK 仅记录这个标记，不负责自动重连，也不提供累计重试次数。

**[3] `message.msg`**：建连结果使用固定文本，错误记录使用带详细内容的文本模板。

| 值或格式 | 描述 |
| --- | --- |
| `WebSocket connection succeeded` | 成功建立连接，对应 `successFlag=true`。 |
| `WebSocket connection failed` | 建立连接失败，对应 `successFlag=false`。 |
| `WEBSOCKET_ERROR: ...` | 错误正文，包含 `connect`、`readyState` 和具体说明。 |

错误正文中的 `readyState` 来自浏览器的连接状态，没有拆成独立上报字段，取值如下：

| 值 | 状态 | 描述 |
| --- | --- | --- |
| `0` | `CONNECTING` | 正在建立连接。 |
| `1` | `OPEN` | 连接已建立，可以发送数据。 |
| `2` | `CLOSING` | 正在关闭连接。 |
| `3` | `CLOSED` | 连接已关闭，或未能建立连接。 |

浏览器通常不开放完整的网络失败原因，因此正文可能只提示查看控制台。`readyState` 能说明出错时连接处于哪个阶段，不能单独确定是网络、证书还是服务端故障。
