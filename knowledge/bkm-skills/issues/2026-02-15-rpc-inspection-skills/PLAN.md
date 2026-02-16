---
title: RPC 场景巡检 Skills —— 实施方案
tags: [bkm-skills, rpc, inspection, red, trpc, skill-design]
issue: ./README.md
description: RPC 巡检 Skill 的结构设计、工作流编排和领域知识组织方案
created: 2026-02-15
updated: 2026-02-15
---

# RPC 场景巡检 Skills —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 调研

### a. 现有能力盘点

**MCP 工具（已就绪）**：

| 工具 | 用途 | 关键参数 |
|------|------|---------|
| `calculate_by_range` | RPC RED 指标计算、维度下钻、时间对比 | `app_name`, `metric_group_name`, `metric_cal_type`, `group_by`, `where`, `time_shifts`, `options.trpc` |
| `search_spans` | 查询调用链 Span 列表 | `app_name`, `filters`, `sort` |
| `get_trace_detail` | 获取完整 Trace 详情 | `app_name`, `trace_id` |
| `get_span_detail` | 获取单个 Span 详情 | `app_name`, `span_id` |
| `list_apm_applications` | 列出 APM 应用 | `bk_biz_id` |

**领域知识（来自 `bkmonitor_mcp/playground/rpc_skills/`）**：

- **RPC 指标规范**（`metric.md`）：27 个维度字段、4 组原始指标、两种 SDK 的 PromQL 计算方式
- **巡检工作流**（`workflow.md`）：RED 面板巡检、维度下钻通用技巧、趋势分析场景
- **接口文档**（`calculate_by_range.md`）：完整的请求/响应参数、where/group_by 字段映射、主被调模式差异

### b. Skill 设计约束

1. **SDK 差异**：Galileo 用 `delta`，Oteam 用 `cumulative`，影响 `options.trpc.temporality`
2. **主被调差异**：`kind=caller` 和 `kind=callee` 可用的维度字段不同（参见指标规范模式差异/特有字段）
3. **高基数防护**：`group_by` 应避免多维度笛卡尔积，优先单维度 → 确认枚举量 < 100 → 再叠加
4. **Trace 关联映射**：RPC 维度到 Span attributes 存在字段名映射关系

## 0x02 方案设计

### a. Skill 整体结构

```text
bkm-skills/
└── skills/
    └── rpc-inspection/
        └── SKILL.md          ← Skill 主文件
```

### b. Skill 内容编排

SKILL.md 组织为以下模块：

#### 模块 1：前置条件与输入

Skill 触发前需确认的信息：

| 输入项 | 必填 | 说明 |
|--------|------|------|
| `bk_biz_id` | 是 | 业务 ID |
| `app_name` | 是 | APM 应用名（从 `list_apm_applications` 获取） |
| `service_name` | 是 | RPC 服务名 |
| `sdk_type` | 是 | SDK 类型：`galileo`（delta）或 `oteam`（cumulative） |
| `kind` | 否 | 视角：`caller`（主调）或 `callee`（被调），默认 `callee` |
| `time_range` | 否 | 巡检时间范围，默认近 1 小时 |

#### 模块 2：巡检工作流

```text
Step 1: RED 指标概览
  ├─ 请求量 (request_total)
  ├─ 成功率 / 超时率 / 异常率
  ├─ 平均耗时 (avg_duration)
  └─ 耗时分布 (p50 / p95 / p99)
         │
         ▼
Step 2: 异常识别
  ├─ 判断是否存在异常指标（异常率 > 阈值、P99 异常等）
  └─ 若无异常 → 输出健康报告，结束
         │
         ▼
Step 3: 维度下钻
  ├─ 按 callee_method 分组 → 找 TOP N 异常接口
  ├─ 锁定接口 → 按 code 分组 → 分析错误码分布
  ├─ 锁定接口 → 按 instance 分组 → 分析实例差异
  └─ [可选] 按 callee_server/caller_server 分析上下游
         │
         ▼
Step 4: 时间对比
  ├─ 对异常维度组合执行 time_shifts=["0s","1d"] 对比
  └─ 确认是新增异常 or 历史遗留
         │
         ▼
Step 5: 调用链关联（可选）
  ├─ 用异常维度构造 filters → search_spans
  ├─ 取典型错误/高耗时 Span → get_trace_detail
  └─ 分析调用链上下游影响
         │
         ▼
Step 6: 输出巡检报告
```

#### 模块 3：领域知识参考

内嵌到 Skill 中供 Agent 查阅的关键知识：

**a) SDK 类型与 temporality 映射**

| SDK 类型 | temporality | 说明 |
|----------|------------|------|
| Galileo | `delta` | 指标类型为 Gauge，使用 `sum_over_time` 计算 |
| Oteam | `cumulative` | 指标类型为 Counter，使用 `increase` 计算 |

**b) 主被调维度差异速查**

| 场景 | `options.trpc.kind` | 独有维度 | Trace 过滤 kind |
|------|---------------------|---------|----------------|
| 主调 | `caller` | `callee_server`, `callee_ip`, `callee_container` | `[3, 4]` |
| 被调 | `callee` | `caller_server`, `caller_ip`, `caller_container` | `[1, 2]` |

**c) 下钻维度优先级**

```text
callee_method → code → instance → callee_server/caller_server → caller_method
```

**d) Trace 字段映射**（RPC 维度 → Span attributes）

| RPC 维度 | Span 属性 |
|----------|-----------|
| `service_name` | `resource.service.name` |
| `caller_service` | `attributes.trpc.caller_service` |
| `callee_method` | `attributes.trpc.callee_method` |
| `code` | `attributes.trpc.status_code` |
| `instance` | `attributes.net.host.ip` |

#### 模块 4：输出格式

巡检报告包含以下部分：

1. **概览表格**：各 RED 指标当前值 + 日环比
2. **异常摘要**：异常指标列表及严重程度
3. **下钻结果**：TOP N 异常接口及其维度分析
4. **建议动作**：基于分析结果给出的下一步操作建议

## 0x03 实施步骤

| # | 步骤 | 产出 | 说明 |
|---|------|------|------|
| 1 | 创建 Skill 骨架 | `skills/rpc-inspection/SKILL.md` | 按模块 1~4 编排 Skill 文件 |
| 2 | 编写巡检工作流 | Skill 模块 2 | 详细描述每个 Step 的 MCP 工具调用方式和参数构造逻辑 |
| 3 | 内嵌领域知识 | Skill 模块 3 | 从 `playground/rpc_skills/` 提炼并结构化 |
| 4 | 定义输出规范 | Skill 模块 4 | 标准化巡检报告格式 |
| 5 | 端到端验证 | 验证记录 | 使用真实服务数据触发完整巡检流程 |

## 0x04 参考

- [RPC 服务巡检工作流](./references/workflow.md)、[RPC 指标规范](./references/metric.md)、[Calculate By Range 接口文档](./references/calculate_by_range.md)
- MCP 工具文档：`calculate_by_range`、`search_spans`、`get_trace_detail`
- Skill 规范：`.cursor/skills/bk-mcp-builder/SKILL.md`

---
*制定日期：2026-02-15*
