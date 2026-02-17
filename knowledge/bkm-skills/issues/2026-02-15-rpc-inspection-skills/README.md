---
title: RPC 场景巡检 Skills
tags: [bkm-skills, rpc, inspection, red, trpc]
description: 基于蓝鲸监控 MCP 工具构建 RPC 服务健康巡检 Skill，覆盖 RED 指标分析与维度下钻
created: 2026-02-15
updated: 2026-02-16
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
    - 即时查询技术参考：新建 `references/use_red_summary.md`。
    - 注 1：calculate_by_range 接口，无需按时间范围分片。
- 维度下钻：增加最佳实践，给出典型的维度下钻路径和脚本调用示例；增加使用示例到 `use_metrics.md` 和 `use_red_summary.md`。
- 波动下钻：增加最佳实践，给出典型的波动下钻分析路径和脚本调用示例。
- 时间对比：增加使用示例到 `use_metrics.md` 和 `use_red_summary.md`。
- 调用链关联：
    - 调用链规范：参考 `references/trace_protocol.md`，将 [Calculate By Range](./references/calculate_by_range.md) 中字段映射部分挪过来。
    - 脚本：参考 `scripts/fetch_events.py`，基于 MCP 工具 `search_spans` 设计 `fetch_spans.py`。
    - 调用链查询技术参考：参考 `references/use_traces.md`，增加调用链关联的使用示例。

### b. 约束

- 遵循 `skill-creator` 规范。
- 参考 `bk-ci-helper` 的工程实践，保持高质量的文档和脚本设计。
- 执行方案提供脚本名、参数设计（表格）和示例调用，供进一步讨论和确认。

## 0x03 产物结构与对标关系

以 `bk-ci-helper`（路径 `skills/bk-ci-helper`）为最佳实践模板，新 Skill 产物结构及对标关系如下：

```text
skills/rpc-inspection/
├── SKILL.md                              # 主文件：前置条件、工具选择指南、巡检工作流、案例
├── references/
│   ├── metric_protocol.md                # RPC 指标规范（维度 + 指标 + SDK 差异）
│   ├── trace_protocol.md                 # Span/Trace 字段协议（含 RPC 维度 → Span 属性映射）
│   ├── use_metrics.md                    # 时序查询技术参考（脚本参数、PromQL 示例、下钻/对比技巧）
│   ├── use_red_summary.md                # 即时查询技术参考（脚本参数、维度下钻、时间对比示例）
│   └── use_traces.md                     # 调用链查询技术参考（脚本参数、Lucene 示例）
└── scripts/
    ├── fetch_metrics.py                  # 【复制】时序查询，封装 execute_range_query
    ├── fetch_red_summary.py              # 【新建】即时查询，封装 calculate_by_range（无需时间分片）
    └── fetch_spans.py                    # 【新建】调用链查询，封装 search_spans（--query-string Lucene）
```

**对标 `bk-ci-helper` 映射表**：

| bk-ci-helper 文件 | RPC Skill 对应文件 | 操作 | 说明 |
|---|---|---|---|
| `references/metric_protocol.md` | `references/metric_protocol.md` | 新建 | 从 `metric.md` 整理，RPC 维度 + 指标 + SDK temporality 差异 |
| `references/event_protocol.md` | `references/trace_protocol.md` | 新建 | Span/Trace 字段协议，含 `calculate_by_range.md` 中的维度→Span 属性映射、kind 过滤规则 |
| `references/use_metrics.md` | `references/use_metrics.md` | 新建 | 时序查询技术参考，增加 RPC PromQL 示例、维度下钻和时间对比技巧 |
| - | `references/use_red_summary.md` | 新建 | 即时查询技术参考，`fetch_red_summary.py` 用法、维度下钻和时间对比示例 |
| `references/use_events.md` | `references/use_traces.md` | 新建 | 调用链查询技术参考，含 `fetch_spans.py` 使用和 Lucene 示例 |
| `scripts/fetch_metrics.py` | `scripts/fetch_metrics.py` | 复制 | 通用脚本，封装 `execute_range_query`，支持 `--instant` |
| `scripts/fetch_events.py` | `scripts/fetch_spans.py` | 新建 | 封装 `search_spans`，通过 `--query-string` 暴露 Lucene 查询，不暴露 `filters` |
| - | `scripts/fetch_red_summary.py` | 新建 | 封装 `calculate_by_range`，无需按时间分片 |
| `SKILL.md` | `SKILL.md` | 新建 | 主文件：前置条件、工具选择指南、巡检工作流、案例 |

### 关键设计决策

| # | 决策点 | 结论 |
|---|---|---|
| 1 | 时序查询工具 | 复用 `fetch_metrics.py`（封装 `execute_range_query`），RPC PromQL 写法参照 `metric.md`；技术参考见 `use_metrics.md` |
| 2 | 即时查询工具 | `calculate_by_range` 是独立 MCP 工具（非 PromQL），需单独脚本 `fetch_red_summary.py`，无需时间分片；技术参考见 `use_red_summary.md` |
| 3 | 调用链查询方式 | `fetch_spans.py` 通过 `--query-string` 传递 Lucene 语法，不暴露 `filters` 参数 |
| 4 | SDK 差异处理 | `temporality`（`delta` / `cumulative`）在即时查询脚本中通过参数控制 |
| 5 | 主被调差异 | `kind`（`caller` / `callee`）影响可用维度和 Trace 过滤条件（caller → kind=[3,4]，callee → kind=[1,2]） |

## 0x04 参考

### a. 源文档

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
