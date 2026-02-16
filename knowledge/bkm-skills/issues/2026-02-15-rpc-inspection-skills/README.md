---
title: RPC 场景巡检 Skills
tags: [bkm-skills, rpc, inspection, red, trpc]
description: 基于蓝鲸监控 MCP 工具构建 RPC 服务健康巡检 Skill，覆盖 RED 指标分析与维度下钻
created: 2026-02-15
updated: 2026-02-15
---

# RPC 场景巡检 Skills

## 0x01 背景

### a. Why

蓝鲸监控已通过 MCP Server 暴露了一系列 APM 工具（`calculate_by_range`、`search_spans`、`get_trace_detail` 等），具备 RPC 服务指标查询、维度下钻和调用链分析的完整能力。

当前 `bkmonitor_mcp` 项目的 `playground/rpc_skills/` 已沉淀了 RPC 巡检的工作流和领域知识（指标规范、RED 分析方法、下钻技巧），但仍以散落文档形式存在，未转化为可被 AI Agent 直接执行的结构化 Skill。

### b. 目标

构建一个 RPC 场景巡检 Skill，包含以下原子能力：
* **时序查询**：掌握 [RPC 指标规范](./references/metric.md) 中的指标及维度，精通服务 RED 趋势的 PromQL 查询。
* **即时查询**：基于 [Calculate By Range](./references/calculate_by_range.md) 查询一段时间内的 RED 汇总情况（例如给定时间范围内的总请求量、成功率、超时率、异常率、耗时分布等）。
* **维度下钻**：通过对「时序查询」「即时查询」增加聚合维度（如 `callee_method`、`code`、`instance`）观察异常数值分布，渐进式增加异常条件，定位异常根因。
* **波动下钻**：对曲线波动或毛刺的时间范围进行聚焦，分析该时间段的 RED 指标变化情况，识别异常发生的具体时间点和相关维度分布。
* **时间对比**：通过增加日环比（1d）、周环比（1w）等偏移量，对比分析，识别新增异常。
* **调用链关联**：使用异常维度组合（如 `callee_method: xxx AND code: 5xx`）作为 Lucene 查询条件，关联 Span，获取完整调用链详情，辅助定位问题根因。

## 0x02 实现路线

### a. 建议的方案

1）原子能力设计

以项目 `bkm-skills` 中的 `bk-ci-helper` 作为最佳实践，以下提及的参考路径均指向该 skill：`skills/bk-ci-helper`。

将上述每个能力点设计为一个独立的 Skill 脚本/文档，明确输入输出和执行步骤，确保原子能力可组合使用：
- 时序查询
    - 指标规范：参考 `references/metric_protocol.md`。
    - 指标查询技术参考：参考 `references/use_metrics.md`。
    - 脚本：`scripts/fetch_metrics.py` 是通用脚本，复制过来。
- 即时查询：
    - 脚本：参考 [Calculate By Range](./references/calculate_by_range.md) 及 `scripts/fetch_metrics.py`，设计脚本执行即时查询。
    - 即时查询技术参考：参考 `references/use_metrics.md`。
    - 注 1：calculate_by_range 接口，无需按时间范围分片。
- 维度下钻：增加最佳实践，给出典型的维度下钻路径和脚本调用示例；增加使用示例到「时序查询技术参考」「即时查询技术参考」。
- 波动下钻：增加最佳实践，给出典型的波动下钻分析路径和脚本调用示例。
- 时间对比：增加使用示例到「时序查询技术参考」「即时查询技术参考」。
- 调用链关联：
    - 调用链规范：参考 `references/event_protocol.md`，将 [Calculate By Range](./references/calculate_by_range.md) 中字段映射部分挪过来。
    - 脚本：参考 `scripts/fetch_events.py`，基于 MCP 工具 `search_spans` 设计 `fetch_spans.py`。
    - 调用链查询技术参考：参考 `references/use_events.md`，增加调用链关联的使用示例。

### b. 约束

- 遵循 `skill-creator` 规范。
- 参考 `bk-ci-helper` 的工程实践，保持高质量的文档和脚本设计。
- 执行方案提供脚本名、参数设计（表格）和示例调用，供进一步讨论和确认。

## 0x03 参考

### a. 文档

- [RPC 服务巡检工作流](./references/workflow.md)
- [RPC 指标规范](./references/metric.md)
- [Calculate By Range 接口文档](./references/calculate_by_range.md)
- MCP 工具：`calculate_by_range`、`search_spans`、`get_trace_detail`、`get_span_detail`

### b. 术语介绍

* RPC：远程过程调用（Remote Procedure Call），一种通过网络请求远程服务器执行特定操作的通信协议。
* Oteam SDK：遵循 OpenTelemetry 规范的 RPC 客户端开发工具包，简化 RPC 服务的集成与调用。
* tRPC：腾讯自研的高性能 RPC 框架，支持多种协议和语言，广泛应用于分布式系统中。
* Taf / Tars：在内外部被⼴泛应⽤，是基于名字服务使⽤ TARS 协议的⾼性能 RPC 开发框架，配套⼀体化的运营管理平台，并通过伸缩调度，实现运维半托管服务。
* RED：一种用于监控微服务性能的指标体系，包括请求速率（Rate）、错误率（Errors）和延迟（Duration）。
