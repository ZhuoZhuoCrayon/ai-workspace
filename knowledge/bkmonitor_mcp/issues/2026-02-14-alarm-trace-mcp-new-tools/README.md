---
title: 告警 & 调用链 MCP 新增部分 tools
tags: [bkmonitor-mcp, alarm, trace, tools]
description: 为蓝鲸监控 MCP Server 的告警和调用链模块新增部分 tools
created: 2026-02-14
updated: 2026-02-15
---

# 告警 & 调用链 MCP 新增部分 tools

## 0x01 背景

### a. Why

当前 MCP 能力有待补充：
- 调用链：增加「调用分析」汇总数据获取 tools。
- 告警：增加告警关联数据（日志/事件/调用链/容器/主机）获取的 tools。

## 0x02 实现路线

### a. 建议的方案

#### 1）更新 `网关配置`

| 后端路径 *[1]* | 接口 *[2]* | 目标 yaml |
|---|---|---|
| `/api/v4/alert_v2/alert/events/` | `fta_web.alert_v2.resources.AlertEventsResource` | `alarm_mcp.yaml` |
| `/api/v4/alert_v2/alert/event_ts/` | `fta_web.alert_v2.resources.AlertEventTSResource` | `alarm_mcp.yaml` |
| `/api/v4/alert_v2/alert/event_tag_detail/` | `fta_web.alert_v2.resources.AlertEventTagDetailResource` | `alarm_mcp.yaml` |
| `/api/v4/alert_v2/alert/k8s_scenario_list/` | `fta_web.alert_v2.resources.AlertK8sScenarioListResource` | `alarm_mcp.yaml` |
| `/api/v4/alert_v2/alert/k8s_metric_list/` | `fta_web.alert_v2.resources.AlertK8sMetricListResource` | `alarm_mcp.yaml` |
| `/api/v4/alert_v2/alert/k8s_target/` | `fta_web.alert_v2.resources.AlertK8sTargetResource` | `alarm_mcp.yaml` |
| `/api/v4/alert_v2/alert/host_target/` | `fta_web.alert_v2.resources.AlertHostTargetResource` | `alarm_mcp.yaml` |
| `/api/v4/alert_v2/alert/traces/` | `fta_web.alert_v2.resources.AlertTracesResource` | `alarm_mcp.yaml` |
| `/api/v4/alert_v2/alert/log_relation_list/` | `fta_web.alert_v2.resources.AlertLogRelationListResource` | `alarm_mcp.yaml` |
| `/api/v4/apm_metric_web/calculate_by_range/` *[3]* | `apm_web.metric.resources.CalculateByRangeResource` | `apm_mcp.yaml` |

* *[1] 后端路径：即 MCP 配置中的 `backend.path`。*
* *[2] 接口：对应后端接口的 import path，可在项目 `bkmonitor` 找到接口的参数及业务逻辑。*
* *[3] `calculate_by_range` 对应的接口文档在项目 `bkmonitor` 下的 `support-files/apigw/docs/zh/calculate_by_range.md`，可作为参数参考。*

#### 2）追加工具介绍到 `MCP介绍&工具说明`

在现有文档中追加新工具说明：
* 告警相关工具 → 追加到 `告警MCP介绍.md`
* 调用链相关工具 → 追加到 `APM Tracing查询工具介绍.md`

### b. 约束

* MCP 生成需遵循 `bk-mcp-builder` skills 的规范。

### c. 澄清记录

| # | 问题 | 结论 |
|---|---|---|
| 1 | `AlertDetailResource` 已有 `get_alert_info` 工具映射到 v1 路径，v2 路径是否需要注册？ | **不需要**，从接口列表中移除。 |
| 2 | `AlertEventTotalResource`（事件总数统计）是否需要单独工具？ | **不需要**，从接口列表中移除。 |
| 3 | 其余接口是否 1:1 映射为独立 MCP 工具？ | **是**，每个接口对应一个独立工具。 |
| 4 | `MCP介绍&工具说明` 文档是新建还是追加？ | **追加**到现有的 `告警MCP介绍.md` 和 `APM Tracing查询工具介绍.md`。 |
| 5 | `calculate_by_range` 参数设计是否需要简化？ | **不需要**，完整暴露所有参数。 |

## 0x03 参考

--