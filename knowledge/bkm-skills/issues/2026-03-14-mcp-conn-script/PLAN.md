---
title: mcp_conn.py — 低 Token 功耗多环境 MCP 调用工具 —— 实施方案
tags: [bk-rpc-inspection, mcp, refactor]
issue: ./README.md
description: 分 3 步实施 mcp_conn.py 创建、存量脚本改造和 SKILL.md 引导修改
created: 2026-03-14
updated: 2026-03-14
---

# mcp_conn.py — 低 Token 功耗多环境 MCP 调用工具 —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 调研

### a. 现状分析

bk-rpc-inspection 中公共函数重复定义分布：

| 函数 | 出现位置 |
|------|---------|
| fix_encoding | fetch_metrics.py, fetch_spans.py |
| get_mcp_client | 全部 3 个脚本 |
| _output_result | 全部 3 个脚本 |

各函数实现基本一致（逻辑相同），收敛后可消除重复。

### b. MCP 服务器命名与环境映射

mcp.json 中的服务器名格式为 `bkm-{env}-{domain}`：
- env: bkte（上云/默认）、bkop（自监控）、bksg（出海/新加坡）
- domain: log-query、metrics-query、alarm、event-query、tracing、metadata-query、dashboard-query、relation-query（共 8 个）

现有脚本中硬编码的旧服务名（如 `bkmonitorv3-prod-metrics-query`）需迁移为新命名。

### c. query_param 工具白名单

34 个工具中有 13 个使用 query_param（其余 21 个使用 body_param）：

| domain | query_param 工具 |
|--------|-----------------|
| metadata-query | list_bcs_clusters, search_spaces |
| dashboard-query | get_dashboard_detail_by_uid, get_dashboard_tree_list |
| metrics-query | list_time_series_metrics |
| tracing | list_apm_applications, get_apm_filter_fields |
| alarm | get_alert_k8s_scenarios, get_alert_k8s_target, get_alert_host_target, get_alert_k8s_metrics, get_alert_info |
| log-query | list_index_sets, get_index_set_fields |

## 0x02 方案设计

### a. mcp_conn.py 架构

位置：`bk-rpc-inspection/scripts/mcp_conn.py`（与 fetch_metrics.py 等脚本同级）

模块结构：

```
mcp_conn.py
├── 常量
│   ├── DOMAINS: 8 个 domain 名称与描述
│   ├── ENV_SERVER_TPL: {"bkte": "bkm-bkte-{domain}", "bkop": "bkm-bkop-{domain}", "bksg": "bkm-bksg-{domain}"}
│   └── QUERY_PARAM_TOOLS: set[str]  # 13 个工具名
├── 公共函数（供同目录脚本 import）
│   ├── fix_encoding(value: Any) -> Any
│   ├── get_mcp_client() -> MCPClient
│   └── output_result(result: dict, output: str) -> None
├── 内部函数
│   ├── resolve_server_name(env: str, domain: str) -> str
│   └── wrap_params(tool_name: str, params: dict) -> dict
└── CLI（argparse）
    ├── listServers: 打印 8 个 domain
    └── call: --env, --server, --tool, --json/--file, --output
```

关键设计点：
- `wrap_params`：查白名单 `QUERY_PARAM_TOOLS`，命中包装 `{"query_param": params}`，否则 `{"body_param": params}`
- `resolve_server_name`：通过 `ENV_SERVER_TPL[env].format(domain=domain)` 拼接完整服务器名
- `get_mcp_client`：从 bk-data-fetcher 导入 MCPClient（通过 sys.path 注入，与现有逻辑一致），统一为单一入口
- CLI 的 `call` 子命令：解析参数 → resolve_server_name → wrap_params → client.call_tool → output_result

CLI 用法：

```bash
python3 mcp_conn.py listServers
python3 mcp_conn.py call --env bkte --server tracing --tool list_apm_applications --json '{"bk_biz_id":"2"}'
python3 mcp_conn.py call --env bkop --server alarm --tool list_alerts --file params.json --output bkmonitor-files/alerts.json
```

### b. 存量脚本改造方案

改造原则：
1. 删除各脚本中的 fix_encoding / get_mcp_client / _output_result 定义
2. mcp_conn.py 与各脚本同目录，直接 `from mcp_conn import ...`
3. 将 `_output_result` 重命名为 `output_result`（去掉下划线前缀）

各脚本改动详情：

| 脚本 | 删除 | 新增导入 | 其他改动 |
|------|------|---------|---------|
| fetch_metrics.py | fix_encoding, get_mcp_client, _output_result | from mcp_conn import fix_encoding, get_mcp_client, output_result | 调用处 _output_result → output_result |
| fetch_red_summary.py | get_mcp_client, _output_result | from mcp_conn import get_mcp_client, output_result | 同上 |
| fetch_spans.py | fix_encoding, get_mcp_client, _output_result | from mcp_conn import fix_encoding, get_mcp_client, output_result | 同上 |

### c. SKILL.md 引导修改方案

**bk-rpc-inspection/SKILL.md**：
- 0x02.b "脚本执行"节：删除 MCPClient 手写脚本模板（约 20 行），替换为 mcp_conn.py call 用法示例
- 删除 body_param/query_param 的 CRITICAL 注释（约 4 行）
- 新增一段 mcp_conn.py 使用说明（约 5 行）

## 0x03 实施步骤

| 阶段 | 改动文件 | 验证方式 | 风险 |
|------|---------|---------|------|
| Step 1: 创建 mcp_conn.py | bk-rpc-inspection/scripts/mcp_conn.py | listServers 输出验证 + call 命令端到端测试（bkte 环境） | 低：新增文件，不影响存量 |
| Step 2: 存量脚本改造 | bk-rpc-inspection/scripts/ 下 3 个脚本 | 各脚本 --help 不报错 + 一次完整查询验证 | 中：导入变更可能影响运行 |
| Step 3: SKILL.md 引导修改 | bk-rpc-inspection/SKILL.md | Agent 执行一次完整巡检验证 | 低：文档变更，可回滚 |

## 0x04 参考

- 现有脚本：bk-rpc-inspection/scripts/（fetch_metrics.py、fetch_red_summary.py、fetch_spans.py）
- MCPClient 基础类：bk-data-fetcher/scripts/mcp_data_fetcher.py
- 参考 CLI：iwiki-doc/scripts/connect_mcp.py（类似的 MCP CLI 工具）
- 关联 Issue：[RPC 巡检 Skill 提速优化](../2026-03-02-rpc-inspection-optimization/README.md)

---
*制定日期：2026-03-14*
