---
title: APM 服务发现
tags: [apm, service, discover, node, endpoint]
description: APM 服务节点发现、端点发现、指标发现等代码片段
language: python
created: 2026-02-09
updated: 2026-02-09
---

# APM 服务发现

## 0x01 关键信息

### a. 适用场景

APM 服务节点发现、端点发现、指标发现的调试和手动触发。

## 0x02 代码片段

### a. 服务节点发现

```python
import datetime
from apm.resources import QuerySpanListResource
from apm.core.discover.node import NodeDiscover
from apm.core.discover.endpoint import EndpointDiscover

bk_biz_id = 19062
app_name = "esp_pubgm_prod"

end_time = int(datetime.datetime.now().timestamp())
begin_time = end_time - int(datetime.timedelta(days=7).total_seconds())

query_params = {
    "bk_biz_id": bk_biz_id, 
    "app_name": app_name, 
    "start_time": begin_time,
    "end_time": end_time,
    "filters": [{"key": "resource.service.name", "operator": "equal", "value": ["esp.pubgm.game"]}],
    "filters": [],
    "exclude_field": ["events"],
    "limit": 10000,
    "es_dsl": {}
}
spans = QuerySpanListResource().request(query_params)["data"]

NodeDiscover(bk_biz_id, app_name).discover(spans)
EndpointDiscover(bk_biz_id, app_name).discover(spans)
```

### b. 批量服务发现

```python
from apm_web.handlers import service_handler

# 过滤出所有未发现 SDK 的服务
service_names = [
    service["topo_key"]
    for service in service_handler.ServiceHandler.list_nodes(100842, "uc-backend") 
    if service["extra_data"]["category"] not in ["db", "messaging"] and service["sdk"] is None
]

for service_name in service_names:
    query_params = {
        "bk_biz_id": bk_biz_id, 
        "app_name": app_name, 
        "start_time": begin_time,
        "end_time": end_time,
        "filters": [{"key": "resource.service.name", "operator": "equal", "value": [service_name]}],
        "exclude_field": ["events"],
        "limit": 10000,
        "es_dsl": {}
    }
    spans = QuerySpanListResource().request(query_params)["data"]
    NodeDiscover(bk_biz_id, app_name).discover(spans)
```

### c. 指标发现

```python
from datetime import datetime, timedelta
from apm.models import MetricDataSource
from apm.core.discover.metric.service import ServiceDiscover

bk_biz_id = 19062
app_name = "esp_pubgm_test"

datasource = MetricDataSource.objects.get(bk_biz_id=bk_biz_id, app_name=app_name)

end_time = int(datetime.now().timestamp())
start_time = end_time - int(timedelta(hours=1).total_seconds())
ServiceDiscover(datasource).discover(start_time, end_time)
```

### d. 查找关联关系

```python
from apm_web.topo.handle.relation.define import SourceK8sPod, SourceService
from apm_web.topo.handle.relation.query import RelationQ

bk_biz_id = 2
app_name = "trpc-cluster-access-demo"
service_name = "bkm.web"
start_time = 1732607026
end_time = 1732610626

result = RelationQ.query(
    RelationQ.generate_q(
        bk_biz_id=bk_biz_id,
        source_info=SourceService(
            apm_application_name=app_name,
            apm_service_name=service_name,
        ),
        target_type=SourceK8sPod,
        start_time=start_time,
        end_time=end_time,
    )
)
```

### e. 手动创建服务节点

```python
from apm.models import TopoNode

servers = ["TestApp.HelloGo"]

bk_biz_id = 5000140
app_name = "bcs_k8s_25973_default"

for server in servers:
    TopoNode.objects.update_or_create(
        bk_biz_id=bk_biz_id,
        app_name=app_name,
        topo_key=server,
        defaults={
            "extra_data": {
                "category": "rpc", 
                "kind": "service", 
                "predicate_value": "", 
                "service_language": "go"
            }
        }
    )
```
