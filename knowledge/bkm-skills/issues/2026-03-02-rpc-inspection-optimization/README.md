---
title: RPC 巡检 Skill 提速优化
tags: [bk-rpc-inspection, optimization, performance]
description: 优化 bk-rpc-inspection Skill 的执行效率，减少工具调用次数和端到端耗时
created: 2026-03-02
updated: 2026-03-02
---

# RPC 巡检 Skill 提速优化

## 0x01 背景

### a. Why

一次标准的"服务健康巡检"执行链路包含 9 个 Phase、~57 次工具调用、端到端耗时 ~38-42s。其中存在大量可消除的假等待、重复进程启动、不必要的串行阻塞和可避免的失败重试。

通过对 4 个维度（Skill 文档结构、数据查询管道、脚本/MCP 交互、工作流编排）的系统审查，识别出以下核心瓶颈：

1. **工作流假等待**：Phase 6（时间对比）可通过 `--offset` 合入 Phase 3 直接消除；Phase 5/7/8 仅依赖 Phase 4 决策可全部并行
2. **脚本重复启动**：6 次 `fetch_red_summary.py` 独立调用（6 次 Python 启动 + 6 次 MCP 连接），固定开销 ~2.4s
3. **告警查询需手写脚本**：每次 7+ 次工具调用，且服务器名不一致导致首次调用必然失败
4. **前置文档过度读取**：强制全量前置读取 ~1,511 行文档，实际利用率 ~43%

### b. 目标

- 端到端耗时：~38-42s → ~14-18s（**-55%**）
- 工具调用次数：~57 次 → ~20-25 次（**-56~65%**）
- Phase 数：9 → 5（**-44%**）
- 失败重试：1 次 → 0 次

## 0x02 实现路线

### a. 建议的方案

分 4 层实施，按投入产出比排序：

**L1 快赢（SKILL.md 改写，零代码改动）**

| 优化点 | 方案 | 预期节省 |
|---|---|---|
| RED 查询合入 `--offset` | 6 次查询直接带 `--offset="1d,1w"` | 8 次调用, ~5s |
| 告警查询用 `CallMcpTool` | 小数据量 MCP 调用改用 Cursor 原生工具 | ~6 次调用 |
| 服务器名映射文档化 | SKILL.md 增加 `user-` 前缀映射表 | 1 次失败重试 |
| `trace_protocol.md` 延迟加载 | 从 CRITICAL 降为 Important | 1 次 Read |
| 脚本自解析 symlink | `os.path.realpath(__file__)` | 1 次 Shell |
| 告警/RT 获取并行化 | 与 RED 查询并行发起 | ~8s 延迟隐藏 |

**L2 脚本改进（改 3 个脚本文件）**

| 优化点 | 方案 | 预期节省 |
|---|---|---|
| 批量多指标查询 | `--metrics` 参数，单进程并发 | 5 次 Shell + 5 次 Read |
| 自动附带交叉验证 | `--with-request-total` | 2-4 次 Shell + Read |
| 预封装告警脚本 | `scripts/fetch_alerts.py` | ~6 次调用 |
| MCPClient Session 复用 | `requests.Session()` | ~2s 连接开销 |

**L3 文档精简（合并/拆分文档）**

| 优化点 | 方案 | 预期节省 |
|---|---|---|
| 合并格式文件 | `common_format.md` + `output_format.md` → `standard_format.md` | 1 次 Read |
| 指标协议内联 | 高频字段摘要内联到 SKILL.md | 1 次 Read |
| use_red_summary 拆分 | 核心 API 140 行 + recipes 176 行 | 前置读取 -56% |

**L4 长期架构（stdout 协议 + 编排重构）**

| 优化点 | 方案 | 预期节省 |
|---|---|---|
| stdout 摘要直出 | 小结果直接 stdout，大数据走文件 | ~10 次 Read |
| Phase 并行编排重构 | 全面重写 0x04 工作流描述 | ~5s |

### b. 约束

- 优化不能降低报告输出质量（格式、超链接、百分比精度等）
- 脚本改动须向后兼容（保留单指标 `--metric` 参数）
- `fetch_red_summary.py` 的交叉验证规则不能因文档拆分而丢失

## 0x03 参考

- 本次巡检执行记录（同会话上文）
- 4 个审查 Agent 的分析报告（同会话上文）
- 当前 SKILL.md：`.cursor/skills/bk-rpc-inspection/SKILL.md`（329 行）
- 当前脚本：`.cursor/skills/bk-rpc-inspection/scripts/`
