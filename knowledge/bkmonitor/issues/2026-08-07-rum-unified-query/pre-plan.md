---
title: RUM Span 详情接口协议草稿
tags: [rum, span, record-detail, api, semconv, figma]
issue: ./README.md
description: 定义 RUM Span 详情构造器、各类型详情 JSON，以及需要异步查询的数据
created: 2026-09-04
updated: 2026-09-06
---

# RUM Span 详情接口协议草稿

## 0x01 公共约定

```json
{
  "bk_biz_id": 2,
  "app_name": "demo",
  "mode": "span",
  "record_id": "7d2f09b6f8bc31aa"
}
```

`POST /rum/search/record_detail/` 根据 `record_id` 返回单条 Span 详情。下文省略 `origin_data`；实际接口继续返回完整原始记录，供 Attributes、Resource 和 Events 原始数据面板使用。

响应由详情头部 `overview` 和有序内容区 `sections` 组成，前端不再按 Span 类型拼装区块。

- `sections[].key` 是区块标识，`type` 取 `field_group`、`timeline`、`event_list` 或 `span_list`，前端按 `key` 翻译标题。
- 详情项使用 `{key, value}`，`key` 引用 `view_config` 字段，后端计算字段以 `detail.*` 命名并注册为虚拟字段。
- 未上报字段直接省略，固定空态使用 `state`，数值 `0` 和布尔值 `false` 必须保留。

## 0x02 详情构造

`SpanLevelHandler` 准备数据，`process(span, related_spans)` 只构造返回值：

```python
BUILDERS = {
    "view": build_view_detail,
    "resource": build_resource_detail,
    "error": build_error_detail,
    "action": build_action_detail,
    "long_task": build_long_task_detail,
    "vital": build_vital_detail,
}


def process(
    span: dict[str, Any],
    related_spans: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    context = DetailContext.from_spans(span, related_spans)
    return BUILDERS.get(context.span_type, build_common_detail)(context)
```

View 详情需要关联数据，查询发生在 `process()` 之前：

```python
span = span_query.get_by_span_id(record_id)
related_spans = []

if get_value(span, "attributes.span_type") == "view":
    view_id = get_value(span, "attributes.view.id")
    if view_id:
        related_spans = span_query.list_by_view_id(view_id)

return process(span, related_spans)
```

- `DetailContext` 兼容打平和嵌套字段，按 `span_id` 去重并排除主 Span。
- View 使用 `attributes.view.version` 最大的生命周期快照，并按 `attributes.vital.metric` 选择 `end_time` 最新的指标。
- `list_by_view_id()` 只查已鉴权应用并返回全部匹配记录，其他 Span 类型不查询关联数据。

## 0x03 各类型详情 JSON

### a. View

```json
{
  "span_id": "34e3b6ff1943346c",
  "span_type": "view",
  "overview": {
    "title": {"key": "attributes.view.url_template", "value": "/orders/:id"},
    "badges": [
      {"key": "attributes.view.loading_type", "value": "initial_load"},
      {"key": "attributes.view.phase", "value": "end"}
    ],
    "items": [
      {"key": "attributes.view.loading_time", "value": 1070},
      {"key": "attributes.view.started_at", "value": 1788451565091}
    ]
  },
  "sections": [
    {
      "key": "view_info",
      "type": "field_group",
      "items": [
        {"key": "app_name", "value": "demo"},
        {"key": "attributes.view.id", "value": "0f8d12b2-7b59-4695-bad7-327567055edf"},
        {"key": "attributes.view.url", "value": "https://example.com/orders/42"},
        {"key": "attributes.view.previous_url_template", "value": "/orders"},
        {"key": "attributes.view.loading_time_source", "value": "auto"},
        {"key": "attributes.session.id", "value": "f4c4fb0c-cf47-4577-ad76-6749c59f7c4e"},
        {"key": "attributes.user.id", "value": "user-10001"},
        {"key": "resource.deployment.environment.name", "value": "production"}
      ]
    },
    {
      "key": "core_result",
      "type": "field_group",
      "items": [
        {"key": "detail.view.request_count", "value": 1},
        {"key": "detail.view.error_count", "value": 1},
        {"key": "detail.view.span_count", "value": 3}
      ]
    },
    {
      "key": "web_vitals",
      "type": "field_group",
      "items": [
        {"key": "TTFB", "value": 710},
        {"key": "FCP", "value": 760},
        {"key": "LCP", "value": 790},
        {"key": "INP", "value": 86},
        {"key": "CLS", "value": 0.023}
      ]
    },
    {
      "key": "page_loading_timing",
      "type": "timeline",
      "items": [
        {"key": "loading_time", "value": {"key": "attributes.view.loading_time", "value": 1070}},
        {
          "key": "ttfb",
          "value": {"key": "TTFB", "value": 710},
          "segments": [
            {"key": "waiting", "duration": {"key": "attributes.vital.ttfb.waiting_duration", "value": 120}},
            {"key": "dns", "duration": {"key": "attributes.vital.ttfb.dns_duration", "value": 20}},
            {"key": "connect", "duration": {"key": "attributes.vital.ttfb.connection_duration", "value": 50}},
            {"key": "request", "duration": {"key": "attributes.vital.ttfb.request_duration", "value": 520}}
          ]
        },
        {"key": "dom_interactive", "value": {"key": "attributes.view.dom_interactive", "value": 720}},
        {
          "key": "dom_content_loaded",
          "value": {"key": "attributes.view.dom_content_loaded", "value": 861}
        },
        {"key": "fcp", "value": {"key": "FCP", "value": 760}},
        {"key": "lcp", "value": {"key": "LCP", "value": 790}},
        {"key": "dom_complete", "value": {"key": "attributes.view.dom_complete", "value": 970}},
        {"key": "load_event", "value": {"key": "attributes.view.load_event", "value": 970}}
      ]
    },
    {
      "key": "span_timeline",
      "type": "span_list",
      "items": [
        {
          "span_id": "7d2f09b6f8bc31aa",
          "span_type": "resource",
          "title": {"key": "attributes.url.template", "value": "/api/orders"},
          "start_time": 1788451565200000,
          "end_time": 1788451565328000,
          "elapsed_time": 128000
        },
        {
          "span_id": "e121536e5ae785a0",
          "span_type": "action",
          "title": {"key": "span_name", "value": "click.submit-btn"},
          "start_time": 1788451565400000,
          "end_time": 1788451565832000,
          "elapsed_time": 432000
        },
        {
          "span_id": "9d199175096474e4",
          "span_type": "error",
          "title": {"key": "attributes.error.message", "value": "Cannot read properties of null"},
          "start_time": 1788451565840000,
          "end_time": 1788451565840000,
          "elapsed_time": 0
        }
      ]
    }
  ]
}
```

- *[1] `TTFB`、`FCP`、`LCP`、`INP` 和 `CLS` 来自同一 `view.id` 下各指标最新的 Vital Span，字段配置复用 `view_config` 中已有的虚拟字段。*
- *[2] 没有 TTFB Vital 时用 `attributes.view.first_byte` 补齐 TTFB，其余指标不做推算。*
- *[3] `detail.view.request_count` 统计 XHR/Fetch Resource，`detail.view.error_count` 统计 Error，`detail.view.span_count` 与 `span_timeline.items` 使用同一份去重后的关联 Span 并排除 View、Vital 和 Session，时间线按 `start_time`、`end_time`、`span_id` 升序排列。*
- *[4] 页面加载时序取 View Span 的 Navigation Timing 字段，并将 FCP、LCP 和 TTFB 合入同一时间轴，TTFB Vital 存在时返回其分段，缺失的阶段直接省略。*
- *[5] `page_loading_timing` 只用于首次加载，路由切换不返回该区块，RUM 数据协议也不能拆出设计稿中的重定向、缓存读取、HTML 下载、DOM 解析和页面稳定阶段，后端不得用相邻时间点反推。*

### b. Resource：XHR 与 Fetch

```json
{
  "span_id": "7d2f09b6f8bc31aa",
  "span_type": "resource",
  "overview": {
    "title": {"key": "attributes.url.template", "value": "/api/orders"},
    "badges": [
      {"key": "attributes.resource.type", "value": "fetch"},
      {"key": "attributes.outcome.type", "value": "success"}
    ],
    "items": [
      {"key": "elapsed_time", "value": 128000},
      {"key": "attributes.http.response.status_code", "value": 200}
    ]
  },
  "sections": [
    {
      "key": "request_info",
      "type": "field_group",
      "items": [
        {"key": "attributes.http.request.method", "value": "POST"},
        {"key": "attributes.url.full", "value": "https://example.com/api/orders"},
        {"key": "attributes.server.address", "value": "example.com"},
        {"key": "trace_id", "value": "14975f27eeb4fa73c41b1c54d89dd92c"},
        {"key": "detail.resource.business_result", "state": "not_collected"}
      ]
    },
    {
      "key": "transfer_info",
      "type": "field_group",
      "items": [
        {"key": "attributes.resource.transfer_size", "value": 3260},
        {"key": "attributes.resource.encoded_body_size", "value": 3120},
        {"key": "attributes.resource.decoded_body_size", "value": 8420},
        {"key": "detail.resource.compression_ratio", "value": 0.6295}
      ]
    },
    {
      "key": "request_timing",
      "type": "timeline",
      "items": [
        {
          "key": "dns",
          "start": {"key": "attributes.resource.dns.start", "value": 1.2},
          "duration": {"key": "attributes.resource.dns.duration", "value": 3.8}
        },
        {
          "key": "connect",
          "duration": {"key": "detail.resource.connect_duration", "value": 4.1}
        },
        {"key": "tls", "state": "not_reported"},
        {
          "key": "first_byte",
          "start": {"key": "attributes.resource.first_byte.start", "value": 9.1},
          "duration": {"key": "attributes.resource.first_byte.duration", "value": 92.6}
        },
        {
          "key": "download",
          "start": {"key": "attributes.resource.download.start", "value": 101.7},
          "duration": {"key": "attributes.resource.download.duration", "value": 26.3}
        }
      ]
    }
  ]
}
```

- *[1] `trace_id` 只表示可以跳转到 Trace 详情，本协议不查询链路上下文。*
- *[2] 未配置业务结果采集规则时返回 `state = not_collected`，请求阶段缺少开始时间或耗时时返回 `state = not_reported`，不能补 `0`。*
- *[3] `detail.resource.connect_duration` 由后端按连接耗时减去 TLS 耗时计算，避免 TLS 被重复统计。*
- *[4] `detail.resource.compression_ratio` 按 `(decoded_body_size - encoded_body_size) / decoded_body_size` 计算，任一字段缺失或解码体积不大于 `0` 时省略。*

### c. Resource：静态资源

```json
{
  "span_id": "2ab0de6ebd6e77f4",
  "span_type": "resource",
  "overview": {
    "title": {"key": "attributes.url.template", "value": "/static/main.js"},
    "badges": [
      {"key": "attributes.resource.type", "value": "script"},
      {"key": "attributes.outcome.type", "value": "success"}
    ],
    "items": [
      {"key": "elapsed_time", "value": 43600},
      {"key": "attributes.resource.transfer_size", "value": 182340}
    ]
  },
  "sections": [
    {
      "key": "resource_info",
      "type": "field_group",
      "items": [
        {"key": "attributes.url.full", "value": "https://example.com/static/main.js"},
        {"key": "attributes.server.address", "value": "example.com"},
        {"key": "attributes.resource.protocol", "value": "h2"}
      ]
    },
    {
      "key": "size_and_delivery",
      "type": "field_group",
      "items": [
        {"key": "attributes.resource.encoded_body_size", "value": 181920},
        {"key": "attributes.resource.decoded_body_size", "value": 642880},
        {"key": "detail.resource.compression_ratio", "value": 0.717},
        {"key": "attributes.resource.cache.hit", "value": true},
        {"key": "attributes.resource.delivery_type", "value": "cache"},
        {"key": "attributes.resource.render_blocking_status", "value": "blocking"}
      ]
    },
    {
      "key": "request_timing",
      "type": "timeline",
      "items": [
        {
          "key": "worker",
          "start": {"key": "attributes.resource.worker.start", "value": 0.4},
          "duration": {"key": "attributes.resource.worker.duration", "value": 2.6}
        },
        {
          "key": "first_byte",
          "start": {"key": "attributes.resource.first_byte.start", "value": 2.6},
          "duration": {"key": "attributes.resource.first_byte.duration", "value": 18.7}
        },
        {
          "key": "download",
          "start": {"key": "attributes.resource.download.start", "value": 21.3},
          "duration": {"key": "attributes.resource.download.duration", "value": 22.3}
        }
      ]
    }
  ]
}
```

非 XHR/Fetch 的 Resource 使用该结构。未知资源类型也按静态资源详情返回，已上报字段不会因为类型未知而丢失。

### d. Error

```json
{
  "span_id": "9d199175096474e4",
  "span_type": "error",
  "overview": {
    "title": {"key": "attributes.error.message", "value": "Cannot read properties of null"},
    "badges": [
      {"key": "attributes.error.source", "value": "window.error"}
    ],
    "items": [
      {"key": "attributes.error.handled", "value": false},
      {"key": "status.code", "value": 2}
    ]
  },
  "sections": [
    {
      "key": "error_info",
      "type": "field_group",
      "items": [
        {"key": "events.attributes.exception.type", "value": "TypeError"},
        {"key": "events.attributes.exception.message", "value": "Cannot read properties of null"},
        {
          "key": "events.attributes.exception.stacktrace",
          "value": "TypeError: Cannot read properties of null\n    at render (main.js:9:654249)"
        }
      ]
    },
    {
      "key": "source_location",
      "type": "field_group",
      "items": [
        {"key": "attributes.code.filepath", "value": "main.js"},
        {"key": "attributes.code.lineno", "value": 9},
        {"key": "attributes.code.column", "value": 654249}
      ]
    },
    {
      "key": "runtime_context",
      "type": "field_group",
      "items": [
        {"key": "resource.service.version", "value": "1.8.3"},
        {"key": "resource.deployment.environment.name", "value": "production"},
        {"key": "attributes.view.url_template", "value": "/orders/:id"}
      ]
    }
  ]
}
```

`overview.title` 优先取 `attributes.error.message`，缺失时回退到 `name = exception` 事件的消息。`error_info` 从该事件读取类型、消息和堆栈，事件消息缺失时再用顶层消息补齐。

### f. Long Task

```json
{
  "span_id": "c49ddfc2ac5214d7",
  "span_type": "long_task",
  "overview": {
    "title": {"key": "attributes.long_task.name", "value": "long-animation-frame"},
    "badges": [
      {"key": "attributes.long_task.entry_type", "value": "long-animation-frame"}
    ],
    "items": [
      {"key": "elapsed_time", "value": 98600},
      {"key": "attributes.long_task.blocking_duration", "value": 48.6}
    ]
  },
  "sections": [
    {
      "key": "task_info",
      "type": "field_group",
      "items": [
        {"key": "attributes.long_task.id", "value": "01J7ZKW5A3J8D5PCQTFYKQ2RT0"},
        {"key": "attributes.action.id", "value": "01J7ZK9VPFJ8DBB7YH56DA7G5X"},
        {"key": "attributes.long_task.render_start", "value": 363397.8},
        {"key": "attributes.long_task.style_and_layout_start", "value": 363420.2}
      ]
    },
    {
      "key": "script_attribution",
      "type": "event_list",
      "items": [
        {
          "name": "long_task.script",
          "timestamp": 1788449833413300,
          "fields": [
            {"key": "events.attributes.long_task.script.duration", "value": 74.6},
            {"key": "events.attributes.long_task.script.invoker", "value": "SPAN.onclick"},
            {"key": "events.attributes.long_task.script.invoker_type", "value": "event-listener"},
            {"key": "events.attributes.long_task.script.source_function_name", "value": "handleSubmit"},
            {"key": "events.attributes.long_task.script.source_url", "value": "https://example.com/main.js"}
          ]
        }
      ]
    }
  ]
}
```

`script_attribution.items` 保留全部 `long_task.script` 事件。前端可按脚本耗时排序，但不能只保留第一条事件。

### e. Action

```json
{
  "span_id": "e121536e5ae785a0",
  "span_type": "action",
  "overview": {
    "title": {"key": "span_name", "value": "click.submit-btn"},
    "badges": [
      {"key": "attributes.action.type", "value": "click"},
      {"key": "attributes.action.frustration.type", "value": ["dead_click"]}
    ],
    "items": [
      {"key": "elapsed_time", "value": 432000},
      {"key": "status.code", "value": 0}
    ]
  },
  "sections": [
    {
      "key": "action_info",
      "type": "field_group",
      "items": [
        {"key": "attributes.action.id", "value": "01J7ZK9VPFJ8DBB7YH56DA7G5X"},
        {"key": "attributes.action.target.name", "value": ".submit-btn"},
        {"key": "attributes.action.target.tag", "value": "button"}
      ]
    },
    {
      "key": "runtime_context",
      "type": "field_group",
      "items": [
        {"key": "attributes.view.url_template", "value": "/checkout"},
        {"key": "resource.device.type", "value": "desktop"}
      ]
    }
  ]
}
```

### g. Vital

```json
{
  "span_id": "ea1ae6490e17fd9d",
  "span_type": "vital",
  "overview": {
    "title": {"key": "attributes.vital.metric", "value": "inp"},
    "badges": [
      {"key": "attributes.vital.metric", "value": "inp"}
    ],
    "items": [
      {"key": "attributes.vital.value", "value": 184}
    ]
  },
  "sections": [
    {
      "key": "metric_detail",
      "type": "field_group",
      "items": [
        {"key": "attributes.vital.inp.input_delay", "value": 18},
        {"key": "attributes.vital.inp.processing_duration", "value": 96},
        {"key": "attributes.vital.inp.presentation_delay", "value": 70},
        {"key": "attributes.vital.inp.interaction_target", "value": ".submit-btn"},
        {"key": "attributes.vital.inp.interaction_type", "value": "pointerup"}
      ]
    }
  ]
}
```

- *[1] Vital 的单位、评级和阈值全部取自 `view_config`，详情接口只返回指标名和原始值。*
- *[2] `metric_detail` 随指标变化：LCP 返回元素和渲染阶段字段，TTFB 返回等待、DNS、连接和请求阶段字段，CLS 没有额外字段时省略该区块。*

Session、WebSocket、Custom 和未知 Span 类型返回公共头部与 `common_info`，其余数据由 `origin_data` 兜底。设计稿没有这些类型的独立详情布局，协议不定义专用结构。

## 0x04 需要异步加载的数据

除 View 按 `view.id` 同步补齐详情外，基础详情不做跨时间聚合。Error 和 Action 的统计数据使用 `POST /rum/search/record_detail_analysis/` 异步加载，并携带页面时间范围：

这里的异步是前端在基础详情返回后发起独立请求，接口直接返回分析结果，不创建后台任务或轮询令牌。

```json
{
  "bk_biz_id": 2,
  "app_name": "demo",
  "mode": "span",
  "record_id": "9d199175096474e4",
  "start_time": 1788449700,
  "end_time": 1788453300,
  "analysis_keys": ["error_impact", "error_trend", "error_versions"]
}
```

### a. Error

```json
{
  "span_id": "9d199175096474e4",
  "blocks": [
    {
      "key": "error_impact",
      "items": [
        {"key": "detail.error.affected_users", "value": 12},
        {"key": "detail.error.affected_sessions", "value": 15},
        {"key": "detail.error.occurrences", "value": 18}
      ]
    },
    {
      "key": "error_trend",
      "points": [
        {"timestamp": 1788449700, "value": 3},
        {"timestamp": 1788450600, "value": 5}
      ]
    },
    {
      "key": "error_versions",
      "current_version": "1.8.3",
      "items": [
        {"version": "1.8.2", "value": 21},
        {"version": "1.8.3", "value": 18}
      ]
    }
  ]
}
```

- *[1] 影响用户数优先按 `attributes.user.id` 去重，User ID 缺失时使用 `attributes.device.id`，影响会话数按 `attributes.session.id` 去重。*
- *[2] 同类错误按错误来源、消息、异常类型、代码位置和页面模板生成指纹，接口只返回同一指纹的统计。*
- *[3] 版本关联只返回各版本的发生次数，不推断“可能修复版本”。*

### b. Action

Action 请求使用 `analysis_keys = ["action_related_counts"]`：

```json
{
  "span_id": "e121536e5ae785a0",
  "blocks": [
    {
      "key": "action_related_counts",
      "items": [
        {"key": "detail.action.related_resources", "value": 4},
        {"key": "detail.action.related_errors", "value": 1},
        {"key": "detail.action.related_long_tasks", "value": 2}
      ]
    }
  ]
}
```

Action 关联数量按应用和 `attributes.action.id` 查询。主 Span 带有 `attributes.session.id` 时，查询同时限制 Session，避免把其他会话的 Span 计入结果。

View 的关联 Span 是基础详情的同步依赖，由 `record_detail` 在调用 `process()` 前查询。Resource、Long Task 和 Vital 的设计内容都能从单条 Span 得到，不需要额外异步接口。链路上下文不在本协议范围内。
