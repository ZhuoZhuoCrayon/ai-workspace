---
title: APM Trace 查询
tags: [apm, trace, span, es]
description: APM Trace 详情查询、Span 查询等代码片段
language: python
created: 2026-02-09
updated: 2026-02-09
---

# APM Trace 查询

## 0x01 关键信息

### a. 适用场景

APM 链路追踪数据查询、Trace 详情获取、ES 查询调试。

## 0x02 代码片段

### a. 查询 Trace 详情

资源：`apm.resources.QueryTraceDetailResource`

```json
{
  "bk_biz_id": 2,
  "app_name": "bkop",
  "trace_id": "2927858ceff8ed8375e9723891a3eba7",
  "displays": [],
  "query_trace_relation_app": false
}
```

### b. 使用 QueryProxy 查询

```python
from apm.core.handlers.query.proxy import QueryProxy

proxy = QueryProxy(2, "sandtrpc")
# 时间范围：1721665179, 1721751579
# trace_id: dc65d13f38263e1b3e31404810296b78
```

### c. ES DSL 查询示例

```python
import time
import datetime
from functools import wraps
from metadata import models
from apm.core.handlers.query.proxy import QueryProxy

def timer(func):
    @wraps(func)
    def inner(*args, **kwargs):
        start: float = time.time()
        ret = func(*args, **kwargs)
        cost = time.time() - start
        print(f"[timer] func -> {func.__name__}, cost -> {round(cost, 3)}")
        return {"ret": ret, "cost": cost}
    return inner

@timer
def execute_dsl(_client, _index, _dsl):
    return _client.search(index=_index, doc_type="_doc", body=_dsl)


end_time = int(datetime.datetime.now().timestamp())
begin_time = end_time - int(datetime.timedelta(hours=1).total_seconds())
begin_time, end_time = begin_time * 1000000, end_time * 1000000

dsl = {
    "query": {
        "bool": {
            "filter": [
                {"range": {"end_time": {"gt": begin_time, "lte": end_time}}},
                {"terms": {"status.code": ["2"]}},
                {"terms": {"resource.service.name": ["example.greeter"]}}
            ]
        }
    },
    "size": 10000,
    "_source": [
        "resource.service.name", "span_name", "trace_id", 
        "events.attributes.exception.type", "events.name", "time"
    ]
}

bk_biz_id = 60
app_name = "trpc-galileo-sdk-access-demo"
proxy = QueryProxy(bk_biz_id, app_name)
storage = models.ESStorage.objects.get(table_id=f"{bk_biz_id}_bkapm.trace_{app_name}")
result = execute_dsl(storage.es_client, f"v2_{bk_biz_id}_bkapm_trace_{app_name}_*_*", dsl)

# 查看 mapping
# storage.es_client.indices.get_mapping(f"v2_{bk_biz_id}_bkapm_trace_{app_name}_*_*")
```

### d. Trace 详情处理

```python
from core.drf_resource import Resource, api
from apm_web.handlers.trace_handler.base import TraceHandler
from apm_web.trace.diagram.service_topo import trace_data_to_service_topo
from apm_web.trace.diagram.topo import trace_data_to_topo_data

validated_request_data = {
    "bk_biz_id": 101067, 
    "app_name": "stress", 
    "trace_id": "00f37ae98580b22ed5582a86b8c271c6", 
    "displays": [], 
    "query_trace_relation_app": False, 
    "bk_username": "fixme:英文名"
}

data = api.apm_api.query_trace_detail({
    "bk_biz_id": validated_request_data["bk_biz_id"],
    "app_name": validated_request_data["app_name"],
    "trace_id": validated_request_data["trace_id"],
    "displays": validated_request_data["displays"],
    "query_trace_relation_app": validated_request_data["query_trace_relation_app"],
})

handled_data = TraceHandler.handle_trace(
    validated_request_data["app_name"],
    data["trace_data"],
    validated_request_data["trace_id"],
    data["relation_mapping"],
    validated_request_data.get("displays"),
    validated_request_data.get("enabled_time_alignment"),
)

topo_data = trace_data_to_topo_data(handled_data["original_data"])
handled_data["topo_relation"] = topo_data["relations"]
handled_data["topo_nodes"] = topo_data["nodes"]
service_topo_data = trace_data_to_service_topo(handled_data["original_data"])
handled_data.update(service_topo_data)
handled_data.update(data.get("options"))
```
