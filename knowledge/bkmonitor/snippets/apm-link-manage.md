---
title: APM 链路管理
tags: [apm, application, config, bk-collector, token, create, delete]
description: APM 应用创建重跑、脏数据清理、配置下发、Token 管理等操作
language: python
created: 2026-02-09
updated: 2026-02-28
---

# APM 链路管理

## 0x01 关键信息

### a. 适用场景

- APM 应用创建失败后的重跑、脏数据清理、状态同步
- APM 应用配置下发到 BK-Collector、平台配置刷新
- APM 日志 DataID Token 生成和解析验证

---

## 0x02 应用管理

### a. 应用创建重跑

```python
bk_biz_id = -4255300
app_name = "production"

from apm.models.application import ApmApplication
from apm.core.handlers.application_hepler import *

es_storage_config = ApplicationHelper.get_default_storage_config(bk_biz_id)
app = ApmApplication.objects.get(bk_biz_id=bk_biz_id, app_name=app_name)

# 重跑异步任务，创建完所有的 datasource
from apm.task.tasks import create_application_async
create_application_async(app.id, es_storage_config, None)

# 同步 saas 状态
from apm_web.models.application import Application
Application.objects.get(bk_biz_id=bk_biz_id, app_name=app_name).sync_datasource()
```

### b. 清理脏数据（老版本）

```python
# api 层清理
from apm.models.application import ApmApplication
ApmApplication.origin_objects.filter(bk_biz_id=bk_biz_id, app_name=app_name).delete()

# web 层清理
from apm_web.models import Application
Application.objects.origin_objects.filter(bk_biz_id=bk_biz_id, app_name=app_name).delete()
```

### c. tRPC 服务统计

```python
import time
from collections import defaultdict
from apm_web.models import Application
from bkm_space.api import SpaceApi
from apm_web.handlers import metric_group

biz_app_stat = defaultdict(lambda: defaultdict(int))
space_mapping = {i["bk_biz_id"]: i["space_name"] for i in SpaceApi.list_spaces_dict()}
apps = Application.objects.filter(bk_biz_id__gt=100394).order_by("bk_biz_id").only("bk_biz_id", "app_name", "app_alias")

result = ""
for app in apps:
    group: metric_group.TrpcMetricGroup = metric_group.MetricGroupRegistry.get(
        metric_group.GroupEnum.TRPC, app.bk_biz_id, app.app_name
    )
    service_cnt = len(group.fetch_server_list())
    if service_cnt:
        result += f"{app.bk_biz_id}, {space_mapping[app.bk_biz_id]}, {app.app_name}, {app.app_alias}, {service_cnt}\n"
    time.sleep(0.1)

print(result)
```

### d. 自定义指标缓存重置

```python
import time
from django.core.cache import caches

from apm_web.constants import ApmCacheKey
from apm_web.handlers.metric_group import MetricHelper
from apm_web.models import Application
from bkmonitor.utils.common_utils import compress_and_serialize, deserialize_and_decompress
from constants.apm import TelemetryDataType

cache_agent = caches["redis"]
application = Application.objects.get(bk_biz_id=-4249653, app_name="testglib")

bk_biz_id = application.bk_biz_id
application_id = application.application_id
result_table_id = application.fetch_datasource_info(
    TelemetryDataType.METRIC.value, attr_name="result_table_id"
)

monitor_info = MetricHelper.get_monitor_info(bk_biz_id, result_table_id)
cache_key = ApmCacheKey.APP_SCOPE_NAME_KEY.format(bk_biz_id=bk_biz_id, application_id=application_id)
cached_data = cache_agent.get(cache_key)
old_monitor_info = deserialize_and_decompress(cached_data) if cached_data else {}
merged_monitor_info = MetricHelper.merge_monitor_info(monitor_info, old_monitor_info)
cache_agent.set(cache_key, compress_and_serialize(merged_monitor_info))
cache_agent.expire(cache_key, 60 * 60 * 72)
```

---

## 0x03 配置下发

### a. 应用配置下发

```python
from apm.core.application_config import ApplicationConfig
from apm.models import ApmApplication

bk_biz_id = 2
app_name = "trpc-cluster-access-demo"

app = ApmApplication.objects.get(bk_biz_id=bk_biz_id, app_name=app_name)
# ApplicationConfig.refresh([app])
ApplicationConfig.refresh_k8s([app])

# 查看订阅配置
from apm.models.subscription_config import SubscriptionConfig
c = SubscriptionConfig.objects.filter(bk_biz_id=bk_biz_id, app_name=app_name).first()
```

### b. 下发 span_name 归一化规则

通过 `custom_service_config` 配置正则匹配规则，将高基数 URL / span_name 归一化为低基数路径。

```python
import json
from apm.models.config import *
from apm.models.application import *
from apm.core.application_config import *

bk_biz_id = 19062
app_name = "esp_pubgm_prod"

app_config = {"custom_service_config": {"name": "service_discover/common", "rules": [
    {
        "service": "None", "type": "http", "match_type": "regex",
        "predicate_key": "span_name", "match_key": "span_name",
        "span_kind": "SPAN_KIND_CLIENT",
        "match_groups": [{"destination": "span_name", "source": "path"}],
        "rule": {"regex": r"^(?P<path>/checkLogin\.php)"},
    },
    {
        "service": "None", "type": "http", "match_type": "regex",
        "predicate_key": "span_name", "match_key": "span_name",
        "span_kind": "SPAN_KIND_CLIENT",
        "match_groups": [{"destination": "span_name", "source": "path"}],
        "rule": {"regex": r"^(?P<path>/v4/openim/batchsendmsg)"},
    },
    {
        "service": "None", "type": "http", "match_type": "regex",
        "predicate_key": "span_name", "match_key": "span_name",
        "span_kind": "SPAN_KIND_CLIENT",
        "match_groups": [{"destination": "span_name", "source": "path"}],
        "rule": {"regex": r"\bsCloudApiName=(?P<path>[^&\s]+)"},
    },
    {
        "service": "None", "type": "http", "match_type": "regex",
        "predicate_key": "span_name", "match_key": "span_name",
        "span_kind": "SPAN_KIND_CLIENT",
        "match_groups": [{"destination": "span_name", "source": "path"}],
        "rule": {"regex": r"^(?P<path>/v2/profile/userinfo)"},
    },
    {
        "service": "None", "type": "http", "match_type": "regex",
        "predicate_key": "span_name", "match_key": "span_name",
        "span_kind": "SPAN_KIND_CLIENT",
        "match_groups": [{"destination": "span_name", "source": "path"}],
        "rule": {"regex": r"^(?P<path>/v2/profile/openid2uid)"},
    },
    {
        "service": "None", "type": "http", "match_type": "regex",
        "predicate_key": "span_name", "match_key": "span_name",
        "span_kind": "SPAN_KIND_CLIENT",
        "match_groups": [{"destination": "span_name", "source": "path"}],
        "rule": {"regex": r"^(?P<path>/v2/auth/verify_login)"},
    },
    {
        "service": "None", "type": "http", "match_type": "regex",
        "predicate_key": "span_name", "match_key": "span_name",
        "span_kind": "SPAN_KIND_CLIENT",
        "match_groups": [{"destination": "span_name", "source": "path"}],
        "rule": {"regex": r"^(?P<path>/audit\d+/_doc)"},
    },
    {
        "service": "None", "type": "http", "match_type": "regex",
        "predicate_key": "span_name", "match_key": "span_name",
        "span_kind": "SPAN_KIND_CLIENT",
        "match_groups": [{"destination": "span_name", "source": "path"}],
        "rule": {"regex": r"^(?P<path>/matchauth\d+/_doc)"},
    },
    {
        "service": "None", "type": "http", "match_type": "regex",
        "predicate_key": "span_name", "match_key": "span_name",
        "span_kind": "SPAN_KIND_CLIENT",
        "match_groups": [{"destination": "span_name", "source": "path"}],
        "rule": {"regex": r"^(?P<path>/orgscores\d+/_doc)"},
    },
]}}

NormalTypeValueConfig.refresh_config(
    bk_biz_id, app_name, AppConfigBase.APP_LEVEL, app_name,
    [{"type": ConfigTypes.ALL_APP_CONFIG, "value": json.dumps(app_config)}],
    need_delete_config=False,
)

applications = list(ApmApplication.objects.filter(bk_biz_id=bk_biz_id, app_name=app_name))
ApplicationConfig.refresh_k8s(applications)
```

### c. 平台配置下发

```python
from apm.core.platform_config import PlatformConfig
PlatformConfig.refresh("system")
```

### d. 查询 Span 分组统计

```python
from apm.models.datasource import TraceDataSource

a = TraceDataSource.objects.filter(bk_biz_id=2, app_name="trpc-cluster-access-demo")[0]
a.query_span_with_group_keys(1745757127, 1745760727, group_keys=["trpc_callee_method"])
```

返回结果示例：

```json
[
  {
    "key": {"trpc_callee_method": "AddItem"},
    "doc_count": 9296,
    "avg_duration": {"value": 29287.11252151463},
    "sum_duration": {"value": 2.72252998E8},
    "min_duration": {"value": 226.0},
    "max_duration": {"value": 633145.0}
  }
]
```

---

## 0x04 Token 管理

### a. 生成 Token

```python
app_name = 'hpjy-microservice-dev-metric'
log_data_id = 1577881

from apm.models.application import *

self = ApmApplication.objects.get(app_name=app_name)
params = {
    "trace_data_id": self.trace_datasource.bk_data_id,
    "metric_data_id": self.metric_datasource.bk_data_id,
    "bk_biz_id": self.bk_biz_id,
    "app_name": self.app_name,
}
if log_data_id:
    params['log_data_id'] = log_data_id
if self.profile_datasource:
    params["profile_data_id"] = self.profile_datasource.bk_data_id
    print(transform_data_id_to_v1_token(**params))
else:
    print(transform_data_id_to_token(**params))
```

### b. 反解验证 Token

```python
token = "fixme:token"

import collections
from bkmonitor.utils.cipher import AESCipher
from django.conf import settings

x_key = getattr(settings, settings.AES_X_KEY_FIELD)
if settings.SPECIFY_AES_KEY != "":
    x_key = settings.SPECIFY_AES_KEY
a = AESCipher(x_key, settings.BK_DATA_AES_IV)
info = a.decrypt(token).split('bk', 6)

if info[0] == 'v1':
    Token = collections.namedtuple('Token', [
        'version', 'metric_data_id', 'trace_data_id', 
        'log_data_id', 'profile_data_id', 'bk_biz_id', 'app_name'
    ])
    print(Token(*info))
else:
    info = a.decrypt(token).split('bk', 4)
    Token = collections.namedtuple('Token', [
        'metric_data_id', 'trace_data_id', 'log_data_id', 'bk_biz_id', 'app_name'
    ])
    print(Token(*info))
```
