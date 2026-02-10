---
title: UnifyQuery 查询
tags: [unify-query, promql, metrics]
description: UnifyQuery 相关的查询和指标缓存操作
language: python
created: 2026-02-09
updated: 2026-02-09
---

# UnifyQuery 查询

## 0x01 关键信息

### a. 适用场景

使用 UnifyQuery 进行指标查询，更新指标缓存等。

## 0x02 代码片段

### a. UnifyQuery 原始请求

```python
from monitor_web.grafana.resources.unify_query import UnifyQueryRawResource

params = {...}  # UnifyQuery 请求参数
UnifyQueryRawResource().request(params)
```

### b. 更新指标缓存

```python
from metadata import models
from metadata.models.space.space_table_id_redis import SpaceTableIDRedis

tsg = models.TimeSeriesGroup.objects.get(bk_data_id={data_id})
tsg.update_time_series_metrics()
SpaceTableIDRedis().push_table_id_detail(table_id_list=[tsg.table_id], is_publish=True)
```

### c. 指标缓存同步

```python
from core.drf_resource import api
from monitor_web.strategies.metric_list_cache import CustomMetricCacheManager

self = CustomMetricCacheManager("system", 2)
custom_ts_result = api.metadata.query_time_series_group(bk_biz_id=self.bk_biz_id)
apm_extra_tables = self.get_apm_extra_tables(custom_ts_result)

# 日志搜索指标
from monitor_web.strategies.metric_list_cache import BkLogSearchCacheManager
self = BkLogSearchCacheManager("system", "-4228266")
for t in self.get_tables():
    print(t["metric_field_name"])

for t in self.get_tables():
    for m in self.get_metrics_by_table(t):
        print(m["metric_field_name"], m['data_type_label'], m['data_source_label'])
```
