---
title: bk-ci-helper 新增 fetch_alert.py 脚本
tags: [bk-ci-helper, alarm, script]
description: 封装告警详情查询为独立脚本，替代工作流中的 MCPClient 手动调用
created: 2026-02-15
updated: 2026-02-15
---

# bk-ci-helper 新增 fetch_alert.py 脚本

## 0x01 背景

### a. Why

`bk-ci-helper` 的构建机异常告警分析工作流（0x04.a）第 1 步「获取告警详情」需要手动编写 MCPClient 脚本调用 `get_alert_info`，与事件/指标查询已封装为独立脚本（`fetch_events.py`、`fetch_metrics.py`）的模式不一致。

### b. 目标

- 新增 `scripts/fetch_alert.py`，封装告警详情查询，支持 `--biz-id` 和 `--alert-id` 两个参数。
- 更新 `SKILL.md` 工作流示例，用脚本调用替代 MCPClient 手动调用。

## 0x02 实现路线

### a. 建议的方案

1. 参考 `fetch_events.py` 的结构（`get_mcp_client` / `_output_result` / `argparse`），实现 `fetch_alert.py`。
2. 调用 `bkmonitorv3-prod-alarm` 的 `get_alert_info` 工具，参数为 `query_param`（GET 请求）。
3. 在 `SKILL.md → 0x04.a → 1）获取告警详情` 增加脚本调用示例。

### b. 约束

- Python 3.6 兼容
- 复用 `get_mcp_client` / `_output_result` 模式
- `--output` 默认输出到 `bkmonitor-files/`
