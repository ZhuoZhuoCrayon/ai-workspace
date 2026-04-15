---
title: 告警详情页 graph_panel 为空时接口报错
tags: [alert, graph-panel, detail, null, bug]
description: 某些告警本身没有图表时，AlertDetailResource 仍无判空清洗 graph_panel，导致详情接口报错
created: 2026-04-15
updated: 2026-04-15
---

# 告警详情页 graph_panel 为空时接口报错

## 0x01 关键信息

### a. 现象

- 告警详情接口 `/fta/alert/v2/alert/detail/` 返回业务失败。
- 栈信息落在 `AlertDetailResource.clean_graph_panel_where()`，异常为 `AttributeError: 'NoneType' object has no attribute 'get'`。

### b. 根因

- `AIOPSManager.get_graph_panel(alert)` 对“本身无图表”的告警可以合法返回 `None`。
- `AlertDetailResource.perform_request()` 未对 `graph_panel` 判空，
  仍直接调用 `clean_graph_panel_where(graph_panel)`，
  最终在 `graph_panel.get("targets", [])` 处报错。

## 0x02 解决方案

- 在 `packages/fta_web/alert/resources.py` 中为 `clean_graph_panel_where()` 增加空值兜底。
- 保持 `graph_panel=None` 的原有语义不变，只修复详情接口不应因此崩溃的问题。

## 0x03 说明

- 本次触发样例是 `gse_process_event` 告警，`panel=None` 属于预期行为，不是本次需要修复的问题本身。
