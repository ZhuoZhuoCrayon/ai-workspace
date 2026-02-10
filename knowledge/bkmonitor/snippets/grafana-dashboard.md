---
title: Grafana 仪表盘导入
tags: [grafana, dashboard, import]
description: 批量导入 Grafana 仪表盘的代码片段
language: python
created: 2026-02-09
updated: 2026-02-09
---

# Grafana 仪表盘导入

## 0x01 关键信息

### a. 适用场景

批量为业务导入预置的 Grafana 仪表盘。

## 0x02 代码片段

### a. 批量导入蓝盾仪表盘

```python
from monitor_web.grafana.resources.manage import QuickImportDashboard

bk_biz_id = -4219865

dash_names = [
    "bkci/BKCI-构建资源趋势.json", 
    "bkci/BKCI-流水线运行趋势.json", 
    "bkci/BKCI-运行中的任务.json",
    "bkci/BKCI-制品趋势.json"
]

for dash_name in dash_names:
    QuickImportDashboard().request({"bk_biz_id": bk_biz_id, "dash_name": dash_name})
```
