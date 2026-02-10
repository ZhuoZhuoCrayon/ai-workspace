---
title: 策略查询与操作
tags: [strategy, query-config, scan]
description: 扫描和分析策略配置的代码片段
language: python
created: 2026-02-09
updated: 2026-02-09
---

# 策略查询与操作

## 0x01 关键信息

### a. 适用场景

扫描特定类型的策略配置，分析策略条件等。

## 0x02 代码片段

### a. 扫描日志搜索策略

```python
from typing import Any
from bkmonitor.models.strategy import QueryConfigModel, StrategyModel

methods: set[str] = set()
strategy_ids: set[int] = set()
filter_kwargs: dict[str, Any] = {"data_source_label": "bk_log_search"}

for q in QueryConfigModel.objects.filter(**filter_kwargs):
    for cond in q.config.get("agg_condition"):
        # 反选条件 ["nreg", "reg", "include", "exclude", "eq", "neq"]
        if cond.get("method") not in ["nreg", "reg", "include", "exclude", "eq", "neq"]:
            methods.add(cond.get("method"))
            strategy_ids.add(q.strategy_id)

for strategy in StrategyModel.objects.filter(id__in=strategy_ids).order_by("bk_biz_id", "update_user"):
    print(strategy.bk_biz_id, strategy.name, strategy.update_user)
  
print(methods)
```
