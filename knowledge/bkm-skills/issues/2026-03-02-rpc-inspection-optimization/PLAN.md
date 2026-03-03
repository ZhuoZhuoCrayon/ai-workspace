---
title: RPC 巡检 Skill 提速优化 —— 实施方案
tags: [bk-rpc-inspection, optimization, performance]
issue: ./README.md
description: 分 4 层渐进式优化 bk-rpc-inspection Skill 的执行效率
created: 2026-03-02
updated: 2026-03-02
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
| 告警脚本手写 | 写脚本 → 执行 → 失败 → 修复 → 重试 | ~15% |
| 其他（MCP 连接等）| TCP 无复用、symlink 解析 | ~15% |

## 0x02 方案设计

### a. L1 快赢（SKILL.md 编排优化，零代码）

**目标**：仅修改 SKILL.md 和参考文档，不改脚本代码。预期节省 ~15s、~18 次调用。

**改动清单**：

1. **SKILL.md 0x04.b（服务健康巡检 workflow）**
   - Step 1 的 6 次 RED 查询全部追加 `--offset="1d,1w"`，一次返回概览 + 时间对比
   - 删除原 Step 5（时间对比作为独立步骤）
   - Step 3（异常下钻）+ Step 4（时序趋势）+ Step 5（告警关联）标记为可并行
   - 告警查询提前至 Step 1 并行发起

2. **SKILL.md 0x02.b（脚本执行）**
   - 新增 `CallMcpTool` 使用指引：小数据量非批量 MCP 调用优先使用 Cursor 原生 `CallMcpTool`
   - 新增服务器名映射表（`user-` 前缀 vs 无前缀）
   - MCPClient 脚本模板保留，仅用于批量/分页/复杂逻辑场景

3. **SKILL.md 0x01（概述）**
   - `trace_protocol.md` 从 CRITICAL 降级为 Important，在调用链步骤前标记"使用前请阅读"
   - `use_metrics.md` 移至前置读取列表（技术参考，不受格式文件延迟读取约束）

4. **SKILL.md 0x02.b（路径解析）**
   - 简化路径解析描述：脚本自身通过 `os.path.realpath(__file__)` 定位依赖
   - 删除 Step 1-4 的外部 Shell 解析流程

### b. L2 脚本改进

**目标**：修改 3 个脚本文件 + MCPClient。预期额外节省 ~10s、~16 次调用。

**改动清单**：

1. **`fetch_red_summary.py`**
   - 新增 `--metrics` 参数（逗号分隔多指标），与 `--metric` 互斥
   - 内部使用 `concurrent.futures.ThreadPoolExecutor` 并发查询，复用同一 MCPClient
   - 输出格式：`{"metadata": {...}, "metrics": {"request_total": {...}, "success_rate": {...}, ...}}`
   - 新增 `--with-request-total` 标志，比率型指标自动并发查询 `request_total`

2. **`scripts/fetch_alerts.py`（新增）**
   - 预封装告警查询脚本，参数化 `--biz-id`、`--start-time`、`--end-time`、`--query-string`、`--status`
   - 内部处理 `bk_biz_ids` 数组转换
   - Agent 只需传参，无需运行时手写脚本

3. **`mcp_data_fetcher.py`（MCPClient）**
   - `__init__` 中初始化 `self.session = requests.Session()`
   - `call_tool` 使用 `self.session.post()` 替代 `requests.post()`
   - `_resolve_server_name()` 增加 `user-` 前缀自动处理

4. **三个查询脚本的路径解析**
   - `get_mcp_client()` 使用 `Path(__file__).resolve().parent.parent.parent` 替代外部 symlink 解析
   - 删除 SKILL.md 中的外部路径解析步骤

### c. L3 文档精简

**目标**：合并/拆分参考文档，减少前置读取量。预期额外节省 ~3 次调用。

**改动清单**：

1. **合并**：`common_format.md`（125 行）+ `output_format.md`（195 行）→ `standard_format.md`（~230 行）
   - 压缩重复的 Bad/Good 示例对比
   - 巡检场景报告阶段只需读 2 个文件（`standard_format.md` + `inspection_report_format.md`）

2. **内联**：`metric_protocol.md` 高频字段摘要（~20 行）内联到 SKILL.md 0x02.a
   - 5 个常用维度（`callee_method`、`code`、`code_type`、`instance`、`service_name`）
   - 被调指标名（`rpc_server_handled_*`）
   - SDK 映射（delta → `sum_over_time`、cumulative → `increase`）
   - 原文件降级为 Important，非常规字段回退查阅

3. **拆分**：`use_red_summary.md`（316 行）→ 核心 API（~140 行）+ 使用技巧（~176 行）
   - 核心：0x01 脚本说明 + 0x02.e 多指标组装 + 0x02.f 高基数防护
   - 技巧：0x02.a-d 使用示例，按需加载
   - **CRITICAL 交叉验证规则**在 SKILL.md 0x04.a 内联一句提醒，防止延迟加载遗漏

### d. L4 长期架构

**目标**：进一步减少文件中转和串行等待。预期额外节省 ~10 次调用。

1. **stdout 摘要直出**
   - 三个查询脚本新增 `--stdout` 开关
   - 小结果（< 10KB）直接 print 到 stdout，Agent 从 Shell 输出获取
   - 大结果仍走文件流
   - SKILL.md 增加数据量判断策略

2. **查询编排模板**
   - SKILL.md 0x04.b 改为「Stage 化」描述
   - 明确标注每个 Stage 的输入依赖和并行可行性
   - 为"全部正常"的快速路径设计简版流程

## 0x03 实施步骤

| 阶段 | 改动文件 | 验证方式 | 预期效果 |
|---|---|---|---|
| **L1** | SKILL.md、SKILL.md 引用的 reference 文件 | 执行一次巡检，对比工具调用次数和耗时 | ~25s, ~39 次调用 |
| **L2** | `fetch_red_summary.py`、`mcp_data_fetcher.py`、新增 `fetch_alerts.py` | 单元测试 + 端到端巡检验证 | ~18s, ~25 次调用 |
| **L3** | `standard_format.md`（合并）、SKILL.md 内联摘要、`use_red_summary.md` 拆分 | 验证报告输出质量不降级 | ~16s, ~22 次调用 |
| **L4** | 脚本 `--stdout` 支持、SKILL.md Stage 化重写 | 端到端巡检 + 边界场景（大数据量）测试 | ~14s, ~20 次调用 |

## 0x04 参考

- 基线执行记录：本会话上文的巡检执行链路
- 4 个审查 Agent 报告：Skill 结构、查询管道、脚本开销、工作流编排
- 现有 Skill 文件：`.cursor/skills/bk-rpc-inspection/`

---
*制定日期：2026-03-02*
