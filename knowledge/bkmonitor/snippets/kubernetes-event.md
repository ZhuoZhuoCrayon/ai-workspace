---
title: Kubernetes 事件查询
tags: [kubernetes, k8s, event, bcs]
description: 查询 Kubernetes 事件日志和聚合统计
language: python
created: 2026-02-09
updated: 2026-02-09
---

# Kubernetes 事件查询

## 0x01 关键信息

### a. 适用场景

查询 Kubernetes 集群事件日志，按事件类型聚合统计。

## 0x02 代码片段

### a. 按事件类型聚合查询

```python
from core.drf_resource import Resource, api, resource
from api.kubernetes.default import FetchK8sEventLogResource
from constants.event import EventTypeNormal, EventTypeWarning

params = {
    "bcs_cluster_id": "BCS-K8S-00000",
    "start_time": 1726640457,
    "end_time": 1726644057,
    "bk_biz_id": -51
}

def aggregate_by_event_type(params):
    """按事件类型聚合"""
    bk_biz_id = params["bk_biz_id"]
    bcs_cluster_id = params.get("bcs_cluster_id")
    start_time = params["start_time"]
    end_time = params["end_time"]
    
    # 设置按事件类型过滤，仅包含正常和警告
    where = [{"key": "type", "method": "eq", "value": [EventTypeNormal, EventTypeWarning]}]
    # 设置按事件类型聚合
    group_by = "dimensions.type"
    # 设置聚合函数，计算每种事件类型的数量
    select = f"count({group_by}) as {group_by}"
    # 设置为聚合操作
    limit = 0
    
    es_params = {
        "bk_biz_id": bk_biz_id,
        "start_time": start_time,
        "end_time": end_time,
        "where": where,
        "bcs_cluster_id": bcs_cluster_id,
        "limit": limit,
        "select": [select],
        "group_by": [group_by],
    }
    return es_params

es_params = aggregate_by_event_type(params)
FetchK8sEventLogResource().request(es_params)
```
