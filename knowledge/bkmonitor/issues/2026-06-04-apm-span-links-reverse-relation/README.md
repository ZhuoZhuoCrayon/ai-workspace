---
title: APM Span 详情支持 Links 反向关联展示
tags: [apm, span, trace, links, relation, otlp]
description: 通过 TraceID 和 SpanID 过滤正向与反向关联，并统一返回 OpenTelemetry Link 列表
created: 2026-06-04
updated: 2026-06-25
---

# APM Span 详情支持 Links 反向关联展示

## 0x01 背景

### a. Why

OpenTelemetry Links 的数据事实由被观测 Span 上报，当前 Span 详情也按这个事实展示当前 Span 自身携带的 `links`。

异步调用场景下，Link 通常出现在被调方或消费方 Span 上。

用户排查问题时更常从主调方、生产方或主 Trace 树开始定位，只有在打开异步被调方 Span 后才能看到 Link。

这会造成关系入口倒置：数据上报侧是正确的，但排查视角需要把“谁链接到了当前 Trace 或 Span”反向呈现在主调方附近，帮助用户在一棵 Trace 树或一个 Span 详情里完成关联理解。

### b. 目标

- 支持使用可选的 TraceID 和 SpanID 组合过滤 Links。
- 同时返回数据上报侧 Links 和反向关联 Links。
- 接口统一返回 OpenTelemetry Link 列表。

## 0x02 实现路线

### a. 建议的方案

新增 `ListLinkResource`，作为 Span / Trace Links 的统一查询接口。

TraceID 和 SpanID 是独立的可选过滤条件，调用时至少提供一个。

同时传入 TraceID 和 SpanID 时，正向查询使用 Span 顶层 TraceID 与 SpanID 的 `AND` 条件，反向查询使用 Link 内 TraceID 与 SpanID 的 `AND` 条件。

接口不校验 TraceID 与 SpanID 的归属关系。

过滤条件不一致时，存储查询自然返回空数据。

接口合并两类 Link：

- 正向 Link：提取命中 Span 自身上报的 `links[]`。
- 反向 Link：查找 `links[]` 命中过滤条件的来源 Span，再把来源 Span 投影为 OpenTelemetry Link。

### b. 约束

- 本期不改变采集、清洗和存储结构，不要求上报侧补反向索引字段。
- 反向查询必须按 `links` 嵌套语义过滤，`links.trace_id` 与 `links.span_id` 同时过滤时必须命中同一个 Link 对象。
- 第一版优先支持当前 APM 应用内反向查询，跨应用或共享数据源下的反向 Link 作为后续扩展。

## 0x03 参考

- 实施方案：[PLAN.md](./PLAN.md)
- [<源码> bk-monitor/bkmonitor/packages/apm_web/trace/resources.py](https://github.com/TencentBlueKing/bk-monitor/blob/master/bkmonitor/packages/apm_web/trace/resources.py)
- [<源码> bk-monitor/bkmonitor/packages/apm_web/trace/views.py](https://github.com/TencentBlueKing/bk-monitor/blob/master/bkmonitor/packages/apm_web/trace/views.py)
- [<源码> bk-monitor/bkmonitor/apm/resources.py](https://github.com/TencentBlueKing/bk-monitor/blob/master/bkmonitor/apm/resources.py)
- [<源码> bk-monitor/bkmonitor/api/apm_api/default.py](https://github.com/TencentBlueKing/bk-monitor/blob/master/bkmonitor/api/apm_api/default.py)
