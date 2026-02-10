---
title: APM 事件索引集创建
tags: [apm, index-set, log-search, es]
description: 创建 APM 事件索引集的代码片段
language: python
created: 2026-02-09
updated: 2026-02-09
---

# APM 事件索引集创建

## 0x01 关键信息

### a. 适用场景

为 APM 应用创建事件索引集，关联流水线事件、K8s 事件、系统事件等。

## 0x02 代码片段

### a. 创建多事件源索引集

```python
from apps.log_search.handlers.index_set import IndexSetHandler

bk_biz_id = 2
space_uid = "bkcc__2"
storage_cluster_id = 5

IndexSetHandler.create(
    index_set_name=f"{bk_biz_id} APM Test Events",
    space_uid=space_uid,
    storage_cluster_id=storage_cluster_id,
    scenario_id="es",
    view_roles=None,
    indexes=[
        {
            "bk_biz_id": bk_biz_id,
            # 流水线事件
            "result_table_id": f"{bk_biz_id}_bkmonitor_event_1574596_*",
            "result_table_name": None,
            "time_field": "time",
        },
        {
            "bk_biz_id": bk_biz_id,
            # [k8s]蓝鲸7.0(BCS-K8S-00000)
            "result_table_id": f"{bk_biz_id}_bkmonitor_event_1573196_*",
            "result_table_name": None,
            "time_field": "time",
        },
        {
            "bk_biz_id": bk_biz_id,
            # 系统事件
            "result_table_id": "gse_system_event*",
            "result_table_name": None,
            "time_field": "time",
        }
    ],
    username="admin",
    time_field="time",
)
```

### b. 创建单事件源索引集

```python
from apps.log_search.handlers.index_set import IndexSetHandler

bk_biz_id = 2
space_uid = "bkcc__2"
storage_cluster_id = 5

IndexSetHandler.create(
    index_set_name="[k8s]蓝鲸7.0(BCS-K8S-00000)",
    space_uid=space_uid,
    storage_cluster_id=storage_cluster_id,
    scenario_id="es",
    view_roles=None,
    indexes=[
        {
            "bk_biz_id": bk_biz_id,
            "result_table_id": f"{bk_biz_id}_bkmonitor_event_1573196_*",
            "result_table_name": None,
            "time_field": "time",
        },
    ],
    username="admin",
    time_field="time",
)
```

### c. 蓝盾项目空间索引集

```python
from apps.log_search.handlers.index_set import IndexSetHandler

bk_biz_id = -4220213
space_uid = "bkci__bkdevops"
storage_cluster_id = 166

IndexSetHandler.create(
    index_set_name="[测试]蓝盾 dev_rbac",
    space_uid=space_uid,
    storage_cluster_id=storage_cluster_id,
    scenario_id="es",
    view_roles=None,
    indexes=[
        {
            "bk_biz_id": bk_biz_id,
            "result_table_id": f"bkmonitor_{-bk_biz_id}_bkmonitor_event_1581075_*",
            "result_table_name": None,
            "time_field": "time",
        },
    ],
    username="admin",
    time_field="time",
)
```

### d. 扩展蓝盾事件字段

```python
from metadata import models

table_id = "bkmonitor_event_1581128"
bk_data_id = models.DataSourceResultTable.objects.get(table_id=table_id).bk_data_id
es_properties_o = models.ResultTableFieldOption.objects.get(
    table_id=table_id, field_name="event", name="es_properties"
)

es_properties_o.value = '{"content":{"type":"text"},"count":{"type":"integer"},"extra": {"type": "object"}}'
es_properties_o.save()

self = models.ESStorage.objects.get(table_id=table_id)
self.update_index_v2()
self.create_or_update_aliases()

models.ResultTableOption.objects.update_or_create(
    table_id=table_id,
    name="event_content",
    bk_tenant_id='system',
    defaults={"value_type": "dict", "value": '{"content":{},"count":{},"extra":{}}'}
)
data_source = models.DataSource.objects.get(bk_data_id=bk_data_id)
data_source.refresh_consul_config()
```
