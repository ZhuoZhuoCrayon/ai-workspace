---
title: RPC 场景巡检 Skills —— 实施方案
tags: [bkm-skills, rpc, inspection, red, trpc, skill-design]
issue: ./README.md
description: RPC 巡检 Skill 的结构设计、脚本参数规格、references 内容大纲及分步实施计划
created: 2026-02-15
updated: 2026-02-17
---

# RPC 场景巡检 Skills —— 实施方案

> 基于 [README.md](./README.md) 制定，以 `bk-ci-helper`（路径 `skills/bk-ci-helper`）为最佳实践对标。

## 0x01 调研

### a. 现有能力盘点

**MCP 工具（已就绪）**：

| 工具                      | 用途                     | 关键参数                                                                                                   |
|-------------------------|------------------------|--------------------------------------------------------------------------------------------------------|
| `calculate_by_range`    | RPC RED 指标计算、维度下钻、时间对比 | `app_name`, `metric_group_name`, `metric_cal_type`, `group_by`, `where`, `time_shifts`, `options.trpc` |
| `execute_range_query`   | PromQL 时序查询            | `bk_biz_id`, `promql`, `start_time`, `end_time`, `step`                                                |
| `search_spans`          | 查询调用链 Span 列表          | `app_name`, `filters`, `query`, `sort`                                                                 |
| `get_trace_detail`      | 获取完整 Trace 详情          | `app_name`, `trace_id`                                                                                 |
| `get_span_detail`       | 获取单个 Span 详情           | `app_name`, `span_id`                                                                                  |
| `list_apm_applications` | 列出 APM 应用              | `bk_biz_id`                                                                                            |

**领域知识（来自 `bkmonitor_mcp/playground/rpc_skills/`）**：

- **RPC 指标规范**（`metric.md`）：27 个维度字段、4 组原始指标、两种 SDK 的 PromQL 计算方式
- **巡检工作流**（`workflow.md`）：RED 面板巡检、维度下钻通用技巧、趋势分析场景
- **接口文档**（`calculate_by_range.md`）：完整的请求/响应参数、where/group_by 字段映射、主被调模式差异

### b. Skill 设计约束

| # | 约束项                       | 说明                                                                                  |
|---|---------------------------|-------------------------------------------------------------------------------------|
| 1 | SDK 差异                    | Galileo → `delta`（Gauge, `sum_over_time`），Oteam → `cumulative`（Counter, `increase`） |
| 2 | 主被调差异                     | `kind=caller` / `kind=callee` 可用维度不同（参见 `metric_protocol.md` 模式差异/特有字段）             |
| 3 | 高基数防护                     | `group_by` 优先单维度 → 确认枚举量 < 100 → 再叠加，避免笛卡尔积                                         |
| 4 | Trace 关联映射                | RPC 维度 → Span attributes 存在字段名映射关系，且需按 kind 过滤 Span.kind                            |
| 5 | calculate_by_range 无需时间分片 | 区别于 `execute_range_query`（限 24h），该接口自行处理时间范围                                        |
| 6 | Progressive Disclosure    | SKILL.md ≤ 500 行，详细知识拆入 `references/`，按需加载                                          |

## 0x02 产物结构

```text
skills/bk-rpc-inspection/
├── SKILL.md                              # 主文件（≤500 行）
├── references/
│   ├── metric_protocol.md                # RPC 指标规范（维度 + 指标 + SDK 差异）
│   ├── trace_protocol.md                 # Span/Trace 字段协议（含维度 → Span 属性映射）
│   ├── use_metrics.md                    # 时序查询技术参考（脚本用法、PromQL 示例、下钻/对比）
│   ├── use_red_summary.md                # 即时查询技术参考（脚本用法、维度下钻、时间对比）
│   ├── use_traces.md                     # 调用链查询技术参考（脚本用法、Lucene 示例）
│   ├── rpc_metric_examples.md           # 【新建】RPC 场景 PromQL 示例集（按 SDK 分类的 RED 指标 + 维度下钻示例）
│   ├── common_format.md                 # 【新建】通用报告输出规范（关键字段、超链接、可读性、数值格式化）
│   └── output_format.md                 # 【新建】报告输出规范（表格展示、巡检报告模板、下钻报告模板）
│
└── scripts/
    ├── fetch_metrics.py                  # 【复制】时序查询脚本，封装 execute_range_query
    ├── fetch_red_summary.py              # 【新建】即时查询脚本，封装 calculate_by_range
    └── fetch_spans.py                    # 【新建】调用链查询脚本，封装 search_spans
```

## 0x03 脚本设计

### a. `fetch_metrics.py`（复制并裁剪自 `bk-ci-helper`）

从 `bk-ci-helper/scripts/fetch_metrics.py` 复制，**删除 `--instant` 相关逻辑**。即时查询能力由 `fetch_red_summary.py` 更优雅地承接（无需手动构造 PromQL，直接指定 `--metric` 即可）。本脚本专注于时序查询场景。

**参数表**：

| 参数             | 类型  | 必填 | 默认值  | 说明                       |
|----------------|-----|----|------|--------------------------|
| `--biz-id`     | int | 是  | -    | 业务 ID                    |
| `--promql`     | str | 是  | -    | PromQL 查询语句              |
| `--start-time` | int | 是  | -    | 开始时间（Unix 秒）             |
| `--end-time`   | int | 是  | -    | 结束时间（Unix 秒）             |
| `--step`       | str | 否  | `1m` | 查询步长（`1m`/`5m`/`1h`/...） |
| `--output`     | str | 是  | -    | 输出文件路径                   |

**示例**：

```bash
# 时序查询 - 被调请求量趋势（Oteam SDK）
python3 /path/to/scripts/fetch_metrics.py --biz-id=2 \
    --promql='sum(increase(rpc_server_handled_total{service_name="example.greeter"}[1m]))' \
    --start-time=$(($(date +%s) - 3600)) --end-time=$(date +%s) \
    --step="1m" --output="request_total.json"

# 时序查询 - 按接口分组的 P99 耗时趋势（Galileo SDK）
python3 /path/to/scripts/fetch_metrics.py --biz-id=2 \
    --promql='histogram_quantile(0.99, sum by (callee_method, le) (sum_over_time(rpc_server_handled_seconds_bucket{service_name="example.greeter"}[1m])))' \
    --start-time=$(($(date +%s) - 3600)) --end-time=$(date +%s) \
    --step="1m" --output="p99_by_method.json"
```

### b. `fetch_red_summary.py`（新建）

封装 `calculate_by_range` MCP 工具。**无需时间分片**（该接口自行处理时间范围）。

**参数表**：

| 参数               | 类型  | 必填 | 默认值    | 说明                                                                                                                                            |
|------------------|-----|----|--------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| `--biz-id`       | int | 是  | -      | 业务 ID                                                                                                                                         |
| `--app-name`     | str | 是  | -      | APM 应用名                                                                                                                                       |
| `--service-name` | str | 是  | -      | RPC 服务名，脚本内部自动注入为 `where` 条件 `service_name=<value>`                                                                                           |
| `--metric`       | str | 是  | -      | 指标类型：`request_total` / `success_rate` / `timeout_rate` / `exception_rate` / `avg_duration` / `p50_duration` / `p95_duration` / `p99_duration` |
| `--kind`         | str | 是  | -      | 调用视角：`caller` / `callee`                                                                                                                      |
| `--temporality`  | str | 是  | -      | SDK 时间性：`delta`（Galileo）/ `cumulative`（Oteam）                                                                                                 |
| `--start-time`   | int | 否  | now-1h | 开始时间（Unix 秒）                                                                                                                                  |
| `--end-time`     | int | 否  | now    | 结束时间（Unix 秒）                                                                                                                                  |
| `--filter`       | str | 否  | `""`   | 逗号分隔的过滤条件，格式 `key=value`。同 key 多值合并为 OR（如 `"callee_method=a,callee_method=b"`），不同 key 之间为 AND。脚本内部转换为 `where` 列表。 |
| `--group-by`     | str | 否  | `""`   | 逗号分隔的分组字段，如 `callee_method,code`                                                                                                              |
| `--offset`       | str | 否  | `""`   | 逗号分隔的对比偏移量，如 `1d` 或 `1d,1w`，支持 `s（秒）`、`m（分）`、`h（时）`、`d（天）`、`w（周）`、`M（月）`。                                                                     |
| `--output`       | str | 是  | -      | 输出文件路径                                                                                                                                        |

> **设计说明**：
> - `--service-name`：RPC 巡检的高频必传参数，脚本内部自动注入为 `where` 条件 `{"key":"service_name","value":["<value>"],"method":"eq","condition":"and"}`。
> - `--filter`：简化过滤条件传递，避免手写 JSON。`"callee_method=SayHi, code=exception"` 内部转换为 `[{"key":"callee_method","value":["SayHi"],"method":"eq","condition":"and"}, {"key":"code","value":["exception"],"method":"eq","condition":"and"}]`，与 `--service-name` 合并生效。
> - `baseline` 不暴露，脚本内部固定为 `"0s"`（以当前时间点为基准计算增长率）。

**输出格式**：

```json
{
  "metadata": {
    "bk_biz_id": 2,
    "app_name": "trpc-cluster-access-demo",
    "service_name": "example.greeter",
    "metric_cal_type": "request_total",
    "kind": "callee",
    "temporality": "cumulative",
    "start_time": 1763535864,
    "end_time": 1763539464
  },
  "total": 3,
  "data": [
    {
      "dimensions": {"callee_method": "SayHi"},
      "0s": 21907,
      "1d": 21896,
      "growth_rates": {"0s": -0.0, "1d": 0.05},
      "proportions": {"0s": 100.0, "1d": 100.0}
    }
  ]
}
```

**示例**：

```bash
# 按接口分组查看请求量 + 日环比
python3 /path/to/scripts/fetch_red_summary.py --biz-id=2 \
    --app-name="trpc-demo" --service-name="example.greeter" \
    --metric="request_total" \
    --kind="callee" --temporality="cumulative" \
    --group-by="callee_method" --offset="1d" \
    --start-time=$(($(date +%s) - 3600)) --end-time=$(date +%s) \
    --output="red_summary.json"

# 按错误码分组查看异常率（锁定接口 SayHi 后下钻）
python3 /path/to/scripts/fetch_red_summary.py --biz-id=2 \
    --app-name="trpc-demo" --service-name="example.greeter" \
    --metric="exception_rate" \
    --kind="callee" --temporality="cumulative" \
    --filter="callee_method=SayHi" --group-by="code" \
    --output="exception_by_code.json"
```

### c. `fetch_spans.py`（新建）

封装 `search_spans` MCP 工具。通过 `--query-string` 暴露 Lucene 查询能力，**不暴露 `filters` 参数**（由脚本内部将 Lucene 转换为 filters 或直接传 query）。

**核心机制**：参考 `bk-ci-helper/scripts/fetch_events.py` 的时间分片模式：

- **时间分片**：MCP 限制单次查询 ≤86400s，脚本自动将长时间范围拆分为多个窗口逐一拉取
- **分页遍历**：单窗口内通过 offset 分页遍历全部结果（每页 500 条，单窗口上限 10,000 条）
- **跨窗口聚合**：合并所有窗口结果后，按 `--sort` 重排序，再按 `--limit` 截取

**参数表**：

| 参数               | 类型  | 必填 | 默认值             | 说明                                                                                                      |
|------------------|-----|----|-----------------|---------------------------------------------------------------------------------------------------------|
| `--biz-id`       | int | 是  | -               | 业务 ID                                                                                                   |
| `--app-name`     | str | 是  | -               | APM 应用名                                                                                                 |
| `--start-time`   | int | 否  | now-1h          | 开始时间（Unix 秒）                                                                                            |
| `--end-time`     | int | 否  | now             | 结束时间（Unix 秒）                                                                                            |
| `--query-string` | str | 否  | `""`            | Lucene 查询字符串，字段名使用 Span 属性名（如 `attributes.trpc.callee_method:SayHi AND status.code:2`） |
| `--sort`         | str | 否  | `-elapsed_time` | 排序字段，`-` 前缀为降序                                                                                          |
| `--limit`        | int | 否  | 100             | 最大返回条数（跨窗口聚合后裁剪）                                                                                        |
| `--output`       | str | 是  | -               | 输出文件路径                                                                                                  |

**输出格式**：

```json
{
  "metadata": {
    "bk_biz_id": 2,
    "app_name": "trpc-cluster-access-demo",
    "query_string": "attributes.trpc.callee_method:SayHi",
    "start_time": 1763535864,
    "end_time": 1763539464
  },
  "total": 5,
  "spans": [
    {
      "span_id": "abc123",
      "trace_id": "xyz789",
      "span_name": "/SayHi",
      "service_name": "example.greeter",
      "elapsed_time": 1234,
      "start_time": 1763535900000,
      "status.code": 2,
      "status.message": "error: connection refused",
      "trpc.status_code": "141",
      "trpc.status_msg": "connection refused to downstream",
      "trpc.status_type": "framework"
    }
  ]
}
```

**示例**：

```bash
# 查询异常 Span（被调视角）
python3 /path/to/scripts/fetch_spans.py --biz-id=<bk_biz_id> \
    --app-name=<app_name> \
    --query-string='resource.service.name:"<service_name>" AND status.code:2 AND kind:(2 OR 5)' \
    --sort="-elapsed_time" --limit=10 \
    --start-time=$(($(date +%s) - 3600)) --end-time=$(date +%s) \
    --output="error_spans.json"
```

## 0x04 References 内容大纲

### a. `metric_protocol.md` — RPC 指标规范

数据来源：[metric.md](./references/metric.md)。

**内容大纲**：

```markdown
# RPC 指标规范

## 0x01 通用维度
（表格：27 个维度字段，来源 metric.md §1）

## 0x02 指标

### a. 主调指标（rpc_client_handled_*）
（一句话描述什么是「主调」）
（表格）

### b. 被调指标（rpc_server_handled_*）
（一句话描述什么是「被调」）
（表格）

## 0x03 SDK 差异
（表格：SDK、指标类型、聚合示例）
```

### b. `trace_protocol.md` — Span 字段协议

数据来源：[calculate_by_range.md](./references/calculate_by_range.md) §支持的聚合与过滤字段 → Trace 映射字段列。

**内容大纲**：

```markdown
# Span 字段协议

## 0x01 RPC 维度 → Span 属性映射
### a. 通用字段映射表
(表格：service_name → resource.service.name, callee_method → attributes.trpc.callee_method, code → attributes.trpc.status_code, ...)

### b. 模式差异字段映射表
(instance → attributes.net.host.ip, ...)

### c. 模式特有字段映射表
(callee_ip → attributes.net.peer.ip [仅主调], caller_ip → attributes.net.peer.ip [仅被调], ...)

## 0x02 Span Kind 过滤规则
- caller（主调）→ kind=[3 OR 4]（CLIENT + PRODUCER）
- callee（被调）→ kind=[2 OR 5]（SERVER + CONSUMER）
```

### c. `use_metrics.md` — 时序查询技术参考

参考 `bk-ci-helper/references/use_metrics.md` 的结构。

**内容大纲**：

```markdown
# 时序查询技术参考

## 0x01 脚本说明
(fetch_metrics.py 参数表、输出格式，同 bk-ci-helper)

## 0x02 使用技巧
### a. 查询时序数据（Counter 类型指标）
（示例：查询过去一个小时内的请求量，并按「被调接口」分组。）

### b. 查询时序数据（Gauge 类型指标）
（示例：查询过去一个小时内的请求量，并按「被调接口」分组。）

### c. 维度下钻
（示例：增加异常维度（例如「被调接口」）作为过滤条件，进一步对其他维度（例如「错误码」）进行分组，观察异常分布。）

### d. 时间对比
（示例：使用 offset 查询一段时间前的数据，进行环比对比，观察趋势变化。）

### e. 动态计算 step
(_cal_auto_step 函数，同 bk-ci-helper)
```

### d. `use_red_summary.md` — 即时查询技术参考

**内容大纲**：

```markdown
# 即时查询技术参考

## 0x01 脚本说明
(fetch_red_summary.py 参数表、输出格式)

## 0x02 使用技巧

### a. 查询即时数据
（示例：查询过去一个小时内的请求平均耗时，并按「被调接口」分组。）

### b. 维度下钻
（示例：增加异常维度（例如「被调接口」）作为过滤条件，进一步对其他维度（例如「错误码」）进行分组，观察成功率分布。）

### c. 波动下钻
（确定时序数据中的毛刺、徒增等波动场景的时间范围并传入即时查询，观察波动区间内的 RED 指标分布，定位异常维度。）
（示例：时序存在毛刺数据点，使用 <毛刺数据点，毛刺数据点 + interval> 作为时间范围，按「被调接口」分组查询成功率，观察是否存在某个接口的成功率异常降低。）

### d. 时间对比
（增加 offset 参数用于对比昨天、上周等同一时间段的数据，辅助判断当前异常的严重程度和紧急程度。）
（示例：已定位到某某接口的成功率异常，使用 offset="1h、1d" 对比过去一小时和过去一天的成功率，观察当前成功率的异常程度。）

### e. 查询多个即时数据组装表格
（示例：按需查询请求量、成功率、平均耗时、P99 耗时等多个指标，组装成一个表格进行综合分析。）
（示例表格：被调接口、成功率、平均耗时、P99 耗时）

### f. 高基数防护
- 单维度优先，确认枚举量 < 100 再叠加
- 结合 --filter 过滤收窄范围后再 group_by
```

### e. `use_traces.md` — 调用链查询技术参考

参考 `bk-ci-helper/references/use_events.md` 的结构。

**内容大纲**：

```markdown
# 调用链查询技术参考

## 0x01 脚本说明
(fetch_spans.py 参数表、输出格式)

## 0x02 使用技巧

### a. 从 RPC 指标到 Span 关联
（条件转化：引用 trace_protocol.md 中的 RPC 维度 → Span 属性映射关系，构造 Lucene 查询字符串。）
（视角（kind）过滤：主调 → kind:[3 OR 4]，被调 → kind:[2 OR 5]。）
（示例：查询被调视角下特定接口的错误 Span。）

### b. 查询错误、高耗时 Span
- 按 status_code 过滤异常 Span
- 按 elapsed_time 降序排序，找高耗时 Span

### c. Trace 详情分析
- 取典型 Span 的 trace_id → get_trace_detail（MCP 直接调用）
- 分析调用链上下游影响
```

### f. `rpc_metric_examples.md` — RPC 指标使用示例

参考 `bk-ci-helper/references/host_metrics_example.md` 的结构。

**关键规则**：**所有 PromQL 示例必须携带 `service_name="<service_name>"` 作为过滤条件**（不可协商），使用占位符而非样例值。

**内容大纲**：

```markdown
# RPC 指标使用示例

> CRITICAL（不可协商）：所有 PromQL 查询必须携带 service_name="<service_name>" 作为过滤条件。

指标名为四段式：custom:{RT}:__default__:{metric_name}
主被调指标对照：被调 rpc_server_handled_* / 主调 rpc_client_handled_*

## 0x01 被调 RED 查询示例（Counter / Oteam SDK）
（a-f：被调请求量/成功率/超时率/异常率/平均耗时/耗时分布。）

## 0x02 主调 RED 查询示例（Counter / Oteam SDK）
（a-f：主调请求量/成功率/超时率/异常率/平均耗时/耗时分布。）

## 0x03 被调 RED 查询示例（Gauge / Galileo SDK）
（a-f：被调请求量/成功率/超时率/异常率/平均耗时/耗时分布。）

## 0x04 主调 RED 查询示例（Gauge / Galileo SDK）
（a-f：主调请求量/成功率/超时率/异常率/平均耗时/耗时分布。）
```

### g. `common_format.md` — 通用报告输出规范

参考 `bk-ci-helper/references/common_format.md`，结合 RPC 场景调整关键字段和超链接模板。

**内容大纲**：

```markdown
# 通用报告输出规范

## 0x01 超链接
（表格：RPC 场景需超链接的字段 — APM 应用名、服务名、Trace ID，及对应的蓝鲸监控 URL 模板）

## 0x02 各场景关键字段
### a. RED 指标概览
### b. 维度下钻
### c. 调用链关联
（各场景必须/推荐展示的字段清单）

## 0x03 可读性
（耗时格式化、时间戳格式、百分比精度、大数值展示、状态标识，同 bk-ci-helper 规范）
```

### h. `output_format.md` — 报告输出规范

参考 `bk-ci-helper/references/output_format.md`，结合 RPC 场景定义表格模板和巡检报告结构。

**内容大纲**：

```markdown
# 报告输出规范

## 0x01 RED 概览表格
（列定义、排序规则、异常行高亮，附示例表格）

## 0x02 维度下钻表格
（标题格式、维度值 + 指标值 + 占比列、环比数据，附示例表格）

## 0x03 时间对比表格
（多时间点并列、增长率计算，附示例表格）

## 0x04 调用链分析表格
（Trace ID 超链接、关键信息列、异常 Span 展示）

## 0x05 巡检报告模板
（结构化报告章节：概要 → RED 概览 → 异常分析 → 调用链 → 结论，信息简洁规则、大表格截断规则）
```

## 0x05 SKILL.md 内容编排

遵循 Progressive Disclosure 原则：SKILL.md 保持精简（≤ 500 行），仅包含工作流骨架和导航指引，详细知识按需从 `references/` 加载。

### a. SKILL.md 结构

```markdown
---
name: bk-rpc-inspection
description: RPC 服务健康巡检 Skill，基于蓝鲸监控 MCP 工具进行 RED 指标分析、维度下钻、时间对比和调用链关联。触发场景：(1) RPC 服务健康巡检，(2) RPC 指标异常排查（如异常率上升、P99 耗时增加），(3) RPC 接口维度下钻分析，(4) RPC 调用链关联排障。术语：RED（Rate/Errors/Duration）｜tRPC（腾讯 RPC 框架）｜Galileo/Oteam（两种 SDK，影响 temporality 参数）。
---

# RPC 服务巡检指南

## 0x01 概述
(简述 Skill 涵盖的能力：RED 指标查询 + 维度下钻 + 波动分析 + 时间对比 + 调用链关联)

**CRITICAL**：开始之前请完整阅读以下文档：
* 指标相关任务 → references/metric_protocol.md
* 调用链任务 → references/trace_protocol.md

## 0x02 基本操作

### a. 前置条件
- 业务 ID：
  - 直接给定 `bk_biz_id`。
  - 给定名称，调用元数据 MCP（bkmonitorv3-prod-metadata）的 `search_spaces` 工具搜索，获取对应的 `bk_biz_id`。
  - 未提供任何业务信息: 提示需提供项目（业务）名、业务 ID 其中之一。
- APM 应用名：
  - 满足 `^[a-z0-9_-]{1,50}$` 的字符串。
  - 没有提供，调用 APM MCP（bkmonitorv3-prod-tracing）的 `list_apm_applications` 工具列出当前业务下的 APM 应用，提示用户选择。
- SDK 类型（Temporality）：Galileo（伽利略） → `delta`，Oteam（默认） → `cumulative`。
- 调用视角（Kind）：主调 → `caller`，被调 → `callee`，默认被调。
- 结果表（RT）：
  - 取 APM MCP（bkmonitorv3-prod-tracing）的 `list_apm_applications` 接口响应中的 `metric_config.result_table_id` 字段。
  - 预处理：`result_table_id.replace(".", "_").replace("-", "__bk_45__")`。

### b. 脚本执行
(脚本路径确认、绝对路径执行、文件流驱动)

### c. 工程素养
(同 bk-ci-helper)

## 0x03 最佳实践：工具选择指南

### a. RED 指标概览（即时查询）
- 适用场景：统计给定时间范围内的 RED 汇总值，快速判断异常值的维度分布，回答一段时间内「哪些接口/实例存在异常」的问题。
- 数据特点：非时序数据，关注整体分布和增长率，适合快速定位异常维度。查询效率高。
- 推荐工具：fetch_red_summary.py，使用前请阅读 references/use_red_summary.md

### b. RED 指标趋势（时序查询）
- 适用场景：需要观察指标随时间的变化趋势，回答「当前服务的请求量/成功率/耗时等指标在过去一段时间内的变化趋势如何」「异常维度的时序趋势如何」等问题。
- 数据特点：时序数据，关注趋势和波动，适合分析异常维度的变化过程和波动特征。查询效率相对较低，适合缩小时间范围或通过「a. RED 指标概览（即时查询）」先获取特定维度后再查询趋势。
- 推荐工具：fetch_metrics.py，使用前请阅读 references/use_metrics.md

### c. 调用链关联
- 使用场景：需要从异常维度关联到具体 Span/Trace
- 推荐工具：fetch_spans.py，使用前请阅读 references/use_traces.md

## 0x04 常见案例

### a. 异常下钻

### 工作流

Step 1：维度下钻
  → fetch_red_summary.py --filter="<异常维度条件>" --group-by="<待分析维度>"。
  → 确认异常维度的分布情况（如是否集中在某些错误码、某些实例等），作为下一次查询的过滤条件。
  → 重复若干次，尝试锁定异常的最小粒度维度组合（如某个接口 + 某个实例）。

Step 2：异常严重度分析
  → fetch_red_summary.py --offset="<offset>"，对比历史数据，确认新增异常 vs 历史遗留。 

Step 3：调用链关联
  → fetch_spans.py --query-string="<异常维度条件>"，查询典型异常 Span。
  → 从 Span 数据抽样典型 Trace ID，MCP get_trace_detail 获取 Trace 详情，分析调用链上下游影响。

### b. RPC 服务健康巡检

#### 工作流

Step 1: RED 指标概览
  → fetch_red_summary.py 按「被调接口」分组，批量查询：请求量、成功率、异常率、超时率、平均耗时、P99 耗时。
  → 组装概览表格，排序：成功率从低到高，耗时从高到低。

Step 2: 异常识别
  → 选择成功率低、P99 耗时异常的接口，参考「a. 异常下钻」 工作流进行分析。
  → 若无异常 → 输出健康报告，结束。

Step 3: 输出巡检报告。

### c. RPC 服务告警分析

Step 1: 获取告警详情

Step 2：解析告警详情
  → 异常时间范围。
  → 告警维度：选取和指标规范有交集的维度字段，作为后续查询的过滤条件。

Step 3：时序查询
  → fetch_metrics.py 查询异常维度的时序趋势，确认异常的持续时间、波动特征等。

Step 4：维度下钻，参考「a. 异常下钻」工作流。

## 0x05 报告输出规范

**【CRITICAL】** 输出报告前请完整阅读以下规范：
* [通用报告输出规范](references/common_format.md)：超链接、关键字段、可读性。
* [报告输出规范](references/output_format.md)：表格展示、报告模板。
```

## 0x06 实施步骤

### Phase 1：基础设施（脚本 + 协议）

| # | 步骤 | 产出 | 数据来源 | 验收标准 |
|---|------|------|----------|----------|
| 1.1 | 创建 Skill 目录结构 | `skills/bk-rpc-inspection/` 骨架 | - | 目录结构与 0x02 一致 |
| 1.2 | 复制并裁剪 `fetch_metrics.py` | `scripts/fetch_metrics.py` | `bk-ci-helper/scripts/fetch_metrics.py` | 删除 `--instant` 相关逻辑，仅保留时序查询能力，可执行 |
| 1.3 | 实现 `fetch_red_summary.py` | `scripts/fetch_red_summary.py` | 0x03-b 参数设计 + `calculate_by_range` MCP 工具 | 参数表全覆盖，输出格式一致，用真实数据验证 |
| 1.4 | 实现 `fetch_spans.py` | `scripts/fetch_spans.py` | 0x03-c 参数设计 + `search_spans` MCP 工具 | 参数表全覆盖，Lucene query 传递正确，用真实数据验证 |
| 1.5 | 编写 `metric_protocol.md` | `references/metric_protocol.md` | `metric.md` → 按 0x04-a 大纲整理 | 覆盖全部维度/指标/SDK 差异/模式差异 |
| 1.6 | 编写 `trace_protocol.md` | `references/trace_protocol.md` | `calculate_by_range.md` Trace 映射部分 → 按 0x04-b 大纲整理 | 映射表完整（通用 + 差异 + 特有），Lucene 转换规则清晰 |

### Phase 2：技术参考文档

| # | 步骤 | 产出 | 数据来源 | 验收标准 |
|---|------|------|----------|----------|
| 2.1 | 编写 `use_metrics.md` | `references/use_metrics.md` | 0x04-c 大纲 + `bk-ci-helper/references/use_metrics.md` 结构 | 覆盖时序/下钻/对比/波动全场景，每场景有脚本示例 |
| 2.2 | 编写 `use_red_summary.md` | `references/use_red_summary.md` | 0x04-d 大纲 | 覆盖概览/下钻/波动/对比全场景，每场景有脚本示例 |
| 2.3 | 编写 `use_traces.md` | `references/use_traces.md` | 0x04-e 大纲 + `bk-ci-helper/references/use_events.md` 结构 | 覆盖维度转换/错误查询/Trace 分析全场景 |
| 2.4 | 编写 `rpc_metric_examples.md` | `references/rpc_metric_examples.md` | 0x04-f 大纲 | 覆盖 Counter/Gauge 两种类型的 RED 指标 PromQL 示例 |
| 2.5 | 编写 `common_format.md` | `references/common_format.md` | 0x04-g 大纲 + `bk-ci-helper/references/common_format.md` | 超链接模板完整、关键字段覆盖 RED/下钻/调用链场景、格式化规则明确 |
| 2.6 | 编写 `output_format.md` | `references/output_format.md` | 0x04-h 大纲 + `bk-ci-helper/references/output_format.md` | 覆盖 RED 概览/下钻/对比/调用链表格模板，巡检报告模板完整 |

### Phase 3：主文件 + 验证

| # | 步骤 | 产出 | 数据来源 | 验收标准 |
|---|------|------|----------|----------|
| 3.1 | 编写 `SKILL.md` | `SKILL.md` | 0x05 内容编排 | ≤ 500 行，frontmatter 完整，工作流清晰，references 导航正确 |
| 3.2 | 端到端验证 | 验证记录 | 真实 RPC 服务数据 | 完整执行巡检工作流 6 步，每步工具调用成功，报告格式达标 |
| 3.3 | 挑刺复审 | 修正记录 | 全部产出物 | 对照 README 需求逐项检查，确保无遗漏 |

## 0x07 参考

- [需求文档](./README.md)
- 源文档：[workflow.md](./references/workflow.md)、[metric.md](./references/metric.md)、[calculate_by_range.md](./references/calculate_by_range.md)
- 最佳实践：`skills/bk-ci-helper/`（SKILL.md、references/、scripts/）
- Skill 规范：`.cursor/skills/skill-creator/SKILL.md`（Progressive Disclosure、frontmatter、资源组织）
- MCP 工具：`calculate_by_range`、`execute_range_query`、`search_spans`、`get_trace_detail`、`get_span_detail`

---
*制定日期：2026-02-15 ｜ 更新日期：2026-02-17*
