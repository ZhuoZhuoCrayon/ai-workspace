---
title: mcp_conn.py — 低 Token 功耗多环境 MCP 调用工具
tags: [bk-rpc-inspection, mcp, refactor]
description: 收敛 bk-rpc-inspection 脚本中的 MCP 公共逻辑，创建多环境、自动参数包装的统一 CLI 调用工具
created: 2026-03-14
updated: 2026-03-14
---

# mcp_conn.py — 低 Token 功耗多环境 MCP 调用工具

## 0x01 背景

### a. Why

当前存在 4 方面问题：

1）**代码散落重复**：`fix_encoding` / `get_mcp_client` / `_output_result` 三个公共函数在 bk-rpc-inspection 的 3 个脚本中重复定义，每次新增脚本都需复制粘贴。

具体分布：

| 函数 | 出现位置 |
|------|---------|
| `fix_encoding` | fetch_metrics.py、fetch_spans.py |
| `get_mcp_client` | 全部 3 个脚本 |
| `_output_result` | 全部 3 个脚本 |

2）**无多环境支持**：现有脚本硬编码 `bkmonitorv3-prod-*` 服务名（旧命名），而 `~/.cursor/mcp.json` 中实际命名为 `bkm-{env}-{domain}`（env = bkte/bkop/bksg），无法直接切换环境调用。

3）**query_param / body_param 区分丑陋**：当前 SKILL.md 需要用约 4 行 CRITICAL 注释引导 Agent 区分工具参数应传 `query_param` 还是 `body_param`，极易出错（用错会导致后端报"必填字段缺失"但 HTTP 200）。

4）**Skill 引导复杂度高**：SKILL.md 引导 Agent 手写独立 `.py` 脚本调用 MCPClient（含 sys.path 拼接、参数类型区分、结果解析、错误检查 — 约 20 行模板代码），每次消耗约 500-800 Token。

### b. 目标

创建 `mcp_conn.py`（位于 `bk-rpc-inspection/scripts/`），作为低 Token 功耗的多环境监控 MCP 调用工具：

- 收敛公共函数（`fix_encoding` / `get_mcp_client` / `output_result`），消除重复代码
- 支持 `--env` 参数切换 bkte（默认）/ bkop / bksg 环境
- 通过 query_param 白名单自动包装参数，消除手动区分
- 提供 `listServers` / `call` 子命令，将 20 行模板代码缩减为 1 行 CLI 命令
- 改造 bk-rpc-inspection 存量 3 个脚本，从 mcp_conn.py 导入公共函数
- 修改 bk-rpc-inspection/SKILL.md 的引导方式

## 0x02 实现路线

### a. 建议的方案

分 3 步实施：

**Step 1：创建 mcp_conn.py**

位置：`bk-rpc-inspection/scripts/mcp_conn.py`（与 fetch_metrics.py 等脚本同级）

核心能力：

- 从 bk-data-fetcher 的 mcp_data_fetcher.py 导入 MCPClient
- 统一暴露 `fix_encoding` / `get_mcp_client` / `output_result`
- 环境映射：`{"bkte": "bkm-bkte-{domain}", "bkop": "bkm-bkop-{domain}", "bksg": "bkm-bksg-{domain}"}`
- query_param 白名单（共 13 个工具），命中则包装为 `{"query_param": {...}}`，否则 `{"body_param": {...}}`

子命令：

- `listServers`：输出硬编码的 8 个 domain（log-query、metrics-query、alarm、event-query、tracing、metadata-query、dashboard-query、relation-query）
- `call --env <env> --server <domain> --tool <tool> --json '<json>'`：调用 MCP 工具
- `call --env <env> --server <domain> --tool <tool> --file <path.json>`：从文件读取参数

query_param 白名单：

| domain | 工具名 |
|--------|--------|
| metadata-query | `list_bcs_clusters`, `search_spaces` |
| dashboard-query | `get_dashboard_detail_by_uid`, `get_dashboard_tree_list` |
| metrics-query | `list_time_series_metrics` |
| tracing | `list_apm_applications`, `get_apm_filter_fields` |
| alarm | `get_alert_k8s_scenarios`, `get_alert_k8s_target`, `get_alert_host_target`, `get_alert_k8s_metrics`, `get_alert_info` |
| log-query | `list_index_sets`, `get_index_set_fields` |

**Step 2：存量脚本改造**

bk-rpc-inspection 的 3 个脚本删除重复函数定义，改为从 mcp_conn 导入：

| 脚本 | 改动 |
|------|------|
| scripts/fetch_metrics.py | 删除 `fix_encoding`/`get_mcp_client`/`_output_result`，改为 `from mcp_conn import` |
| scripts/fetch_red_summary.py | 删除 `get_mcp_client`/`_output_result`，改为 `from mcp_conn import` |
| scripts/fetch_spans.py | 删除 `fix_encoding`/`get_mcp_client`/`_output_result`，改为 `from mcp_conn import` |

**Step 3：SKILL.md 引导修改**

bk-rpc-inspection/SKILL.md 0x02.b 节 MCPClient 手写模板替换为 `mcp_conn.py call` 命令；删除 body_param/query_param 引导注释。

使用场景：所有 `bkm-` 开头的 MCP 调用统一通过 `mcp_conn.py call` 进行，不再引导手写 MCPClient 脚本。

### b. 约束

- mcp_conn.py 仅处理 `bkm-` 前缀的 MCP 服务器，不覆盖其他 MCP（如 iWiki）
- 存量脚本改造须向后兼容，不改变现有 CLI 参数和输出格式
- query_param 白名单需随 MCP 工具新增同步维护

## 0x03 参考

- 现有脚本：`bk-rpc-inspection/scripts/`（3 个）
- 共享依赖：`bk-data-fetcher/scripts/mcp_data_fetcher.py`（MCPClient 定义）
- 参考实现：`iwiki-doc/scripts/connect_mcp.py`（类似的 MCP CLI 工具）
- MCP 服务器命名规则：`bkm-{env}-{domain}`（mcp.json 中的实际名称）
- 关联 Issue：[RPC 巡检 Skill 提速优化](../2026-03-02-rpc-inspection-optimization/README.md)
