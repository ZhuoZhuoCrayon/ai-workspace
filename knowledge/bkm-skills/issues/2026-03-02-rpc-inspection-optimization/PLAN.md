---
title: RPC 巡检 Skill 提速优化 —— 实施方案
tags: [bk-rpc-inspection, optimization, performance]
issue: ./README.md
description: 分 4 层渐进式优化 bk-rpc-inspection Skill 的执行效率
created: 2026-03-02
updated: 2026-03-14
---

# RPC 巡检 Skill 提速优化 —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 调研

### a. 基线数据

通过实际执行一次完整的"服务健康巡检"（业务 100380 / formal_thkgame_apm / thkgame.CommonCtrl / delta），采集以下基线：

| 指标 | 基线值 |
|---|---|
| Phase 数 | 9 |
| 工具调用次数 | ~57 |
| 端到端耗时 | ~38-42s |
| 前置文档读取 | 9 Read + 1 Shell，~1,511 行 |
| 数据查询脚本调用 | ~20 次 Shell |
| 结果文件读取 | ~20 次 Read |
| 可避免的失败重试 | 1 次 |

### b. 瓶颈分类

| 类别 | 典型问题 | 占总耗时 |
|---|---|---|
| 工作流假等待 | Phase 6 可合入 Phase 3；Phase 5/7/8 可并行 | ~35% |
| 脚本重复启动 | 6 次独立 Python 进程启动（~400ms/次）| ~15% |
| 文件中转开销 | 查询 → 写文件 → Read 读取的三跳模式 | ~10% |
| 前置文档过度读取 | 1,511 行中实际用 ~700 行 | ~10% |

## 0x02 方案设计

### a. L1 快赢（SKILL.md 编排优化，零代码）

**目标**：仅修改 SKILL.md 和参考文档，不改脚本代码。预期节省 ~15s、~18 次调用。

**改动清单**：

1. **SKILL.md 0x04.b（服务健康巡检 workflow）**
   - Step 1 的 6 次 RED 查询全部追加 `--offset="1d,1w"`，一次返回概览 + 时间对比
   - 删除原 Step 5（时间对比作为独立步骤）
   - Step 3（异常下钻）+ Step 4（时序趋势）+ Step 5（告警关联）标记为可并行
   - 告警查询提前至 Step 1 并行发起

2. **SKILL.md 0x01（概述）**
   - `trace_protocol.md` 从 CRITICAL 降级为 Important，在调用链步骤前标记"使用前请阅读"
   - `use_metrics.md` 移至前置读取列表（技术参考，不受格式文件延迟读取约束）

### b. L2 脚本改进

**目标**：`fetch_red_summary.py` 多指标并发查询。预期额外节省 ~10s、~16 次调用。

**改动清单**：

1. **`fetch_red_summary.py`**
   - 移除 `--metric`，新增 `--metrics`（逗号分隔多指标）
   - 内部使用 `concurrent.futures.ThreadPoolExecutor` 并发查询，复用同一 MCPClient
   - 输出格式：`{"metadata": {...}, "metrics": {"request_total": {"total": N, "data": [...]}, ...}}`

### c. L3 文档精简

**目标**：精简参考文档中的冗余示例，减少前置读取量。预期额外节省 ~3 次调用。

**改动清单**：

1. **`rpc_metric_examples.md`**：以按接口分组（`sum by (...)`）作为主示例，移除无分组 `sum(...)` 示例，文件顶部新增维度分组说明
2. **`use_red_summary.md`**：section e（多指标组装表格）压缩为单次 `--metrics` 调用示例

### d. L4 长期架构

**目标**：进一步减少文件中转和串行等待。预期额外节省 ~10 次调用。

1. **查询编排模板**
   - SKILL.md 0x04.b 改为「Stage 化」描述
   - 明确标注每个 Stage 的输入依赖和并行可行性
   - 为"全部正常"的快速路径设计简版流程

## 0x03 实施步骤

| 阶段 | 改动文件 | 验证方式 | 预期效果 |
|---|---|---|---|
| **L1** | SKILL.md、SKILL.md 引用的 reference 文件 | 执行一次巡检，对比工具调用次数和耗时 | ~25s, ~39 次调用 |
| **L2** | `fetch_red_summary.py` | 单元测试 + 端到端巡检验证 | ~18s, ~25 次调用 |
| **L3** | `rpc_metric_examples.md` 精简、`use_red_summary.md` section e 压缩 | 验证文档正确性、报告输出质量不降级 | ~16s, ~22 次调用 |
| **L4** | SKILL.md Stage 化重写 | 端到端巡检 + 边界场景测试 | ~14s, ~20 次调用 |

## 0x04 实施记录

### 2026-03-14：L2 + L3 + mcp_conn 基础设施

分支 `perf/260314_bk_rpc`，3 次提交。

**脚本改进（L2）**：

| 改动 | 效果 |
|---|---|
| `fetch_red_summary.py`：`--metric` → `--metrics`（逗号分隔），ThreadPoolExecutor 并发查询 | 6 次串行脚本调用 → 1 次并发调用 |
| `fetch_red_summary.py`：`main()` 拆分为 `_build_params`/`_query_metric`/`_query_all_metrics`/`_validate_metrics`/`_build_parser` | 可读性提升，单元可测试 |
| `mcp_conn.py`：`_call_tool` 增加 `json.loads` + `response_body` 提取 | 保存解析后的业务数据，不再存原始 MCP 信封 |
| `mcp_conn.py`：`--output` 改为必传，移除 stdout 模式 | 统一文件流，避免大结果截断 |
| `mcp_conn.py`：`list_apm_applications` 后处理自动附加 `promql_rt` 字段 | SKILL.md 不再需要嵌入 Python 转换代码，模型直接引用 |

**文档精简（L3）**：

| 改动 | 效果 |
|---|---|
| `rpc_metric_examples.md`：移除无分组 `sum(...)` 示例，`sum by (...)` 作为唯一主示例 | 文件从 451 行缩减至 ~330 行 |
| `use_red_summary.md`：section e 压缩为单次 `--metrics` 调用 | 移除 4 段重复脚本调用 + 手工合并示例 |
| `SKILL.md`：RT 转换从 Python 代码块简化为一句引用说明 | 前置读取量减少 ~8 行 |

**端到端验证**（bkop 环境业务 2 / trpc-cluster-access-demo / bkm.web / caller）：

- `mcp_conn.py call --tool list_apm_applications` 返回的 `promql_rt` 字段正确
- `fetch_red_summary.py --metrics=...` 6 指标并发查询正常
- 调用链关联、时间对比等后续步骤无回归

**遗留**：

- L1（编排优化）已在更早会话中完成，未在本轮记录
- L4（Stage 化编排）待后续迭代

## 0x05 参考

- 基线执行记录：本会话上文的巡检执行链路
- 4 个审查 Agent 报告：Skill 结构、查询管道、脚本开销、工作流编排
- 现有 Skill 文件：`.cursor/skills/bk-rpc-inspection/`

---
*制定日期：2026-03-02 | 更新：2026-03-14*
