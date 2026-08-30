---
title: APM SaaS 配置
tags: [apm, saas-config, code-redefine, log-relation, log-filter, k8s, workload, django-shell]
description: 记录 APM SaaS 侧返回码重定义、服务关联日志、全局关联日志过滤规则与容器关联导入的配置脚本
language: python
created: 2026-02-09
updated: 2026-08-27
---

# APM SaaS 配置

## 0x01 关键信息

### a. 适用场景

在 Django shell 中批量维护 APM SaaS 配置，覆盖返回码重定义、服务关联日志、全局关联日志过滤条件和容器关联导入。

### b. 使用边界

- 返回码重定义写库后，需要重新构建并发布 APM 配置。
- 服务关联日志脚本使用 `scope=SyncScope.ALL` 和 `is_delete=True`，适合确认脚本已包含应用全量规则的场景。
- 全局关联日志脚本使用 `scope=SyncScope.GLOBAL` 和 `is_delete=False`，只做增改，适合在存量配置上增量补充。
- `LogServiceRelation.value_list` 必须使用 `int` 类型，避免后续按索引集过滤时匹配失败。
- 容器关联脚本默认 `DRY_RUN=True`，`is_delete=True` 只收敛该应用下的 `k8s_event`。

## 0x02 代码片段

### a. 批量设置返回码重定义

```python
from typing import Any

from apm_web.models.service import CodeRedefinedConfigRelation
from apm_web.service.resources import SetCodeRedefinedRuleResource
from apm_web.strategy.dispatch.entity import EntitySet

bk_biz_id: int = 5016858
app_name: str = "tf_test"

# 格式：单个码用逗号分隔，范围用波浪线连接
rules: dict[str, str] = {
    "success": "409,10001~10002,10006,10008~10009,11002~11003,11005,11007,11100~11199,11215,11300~11301,11450~11499,11501,11503,11601~11618,11701~11703,11802,11901~11905,11907~11909,11913~11916,11919~11920,11924,15202~15206,15208~15212,15214~15215,13004",
    "timeout": "",
    "exception": "",
}

# 清除旧配置
CodeRedefinedConfigRelation.objects.filter(bk_biz_id=bk_biz_id, app_name=app_name).delete()

# 为所有服务创建配置
relations: list[CodeRedefinedConfigRelation] = []
for service_name in EntitySet(bk_biz_id, app_name).service_names:
    params: dict[str, Any] = {
        "bk_biz_id": bk_biz_id,
        "app_name": app_name,
        "service_name": service_name,
        "code_type_rules": rules,
    }
    relations.append(CodeRedefinedConfigRelation(kind="callee", **params))
    relations.append(CodeRedefinedConfigRelation(kind="caller", **params))

CodeRedefinedConfigRelation.objects.bulk_create(relations)

# 构建并发布配置
SetCodeRedefinedRuleResource.build_code_relabel_config(bk_biz_id, app_name)
SetCodeRedefinedRuleResource.publish_code_relabel_to_apm(bk_biz_id, app_name)
```

关键调用：

- `build_code_relabel_config` 负责生成最新返回码配置。
- `publish_code_relabel_to_apm` 负责下发到运行侧。

### b. 全量同步服务关联日志

```python
from apm_web.constants import ServiceRelationLogTypeChoices, SyncScope
from apm_web.models import LogServiceRelation

bk_biz_id = 0
app_name = "your_apm_app"

DEFAULT_LOG_INDEX_SETS = [0, 0]

service_groups = [
    {
        "services": [
            "service-a",
            "service-b",
        ],
        "related_bk_biz_id": bk_biz_id,
        "value_list": DEFAULT_LOG_INDEX_SETS,
    },
    {
        "services": ["service-c"],
        "related_bk_biz_id": 0,
        "value_list": [0],
    },
    {
        "services": ["service-d"],
        "related_bk_biz_id": 0,
        "value_list": [0, 0],
    },
]

records = [
    {
        "bk_biz_id": bk_biz_id,
        "app_name": app_name,
        "service_name": service_name,
        "is_global": False,
        "log_type": ServiceRelationLogTypeChoices.BK_LOG,
        "related_bk_biz_id": group["related_bk_biz_id"],
        "value": "",
        "value_list": group["value_list"],
    }
    for group in service_groups
    for service_name in group["services"]
]

service_names = [record["service_name"] for record in records]
assert len(service_names) == len(set(service_names)), "service_name 存在重复配置"

result = LogServiceRelation.sync_relations(
    bk_biz_id=bk_biz_id,
    app_name=app_name,
    records=records,
    scope=SyncScope.ALL,
    is_delete=True,
)

print(result)

for relation in LogServiceRelation.get_relations(
    bk_biz_id,
    app_name,
    service_names=service_names,
):
    print(
        relation["service_name"],
        relation["related_bk_biz_id"],
        relation["value_list"],
    )
```

同步边界：

- 服务关联日志的唯一键包含 `bk_biz_id`、`app_name`、`service_name`、`log_type` 和 `related_bk_biz_id`。
- `scope=SyncScope.ALL` 与 `is_delete=True` 会把当前应用下的记录收敛到 `records`。

### c. 增量补充全局关联日志与过滤规则

为应用配置全局关联日志（`is_global=True`、`service_name=""`），并补充查询时挂上的过滤条件。脚本可重复执行。

```python
from apm_web.constants import ServiceRelationLogTypeChoices, SyncScope
from apm_web.models import Application, LogServiceRelation
from bkmonitor.utils.request import set_request_username

# APM 应用所在业务
BK_BIZ_ID = 0
# 索引集所在业务
RELATED_BK_BIZ_ID = 0
INDEX_SET_IDS = [0, 0]
# ${service_name} 在查询时替换为当前 APM 服务名
ADDITION = [{"field": "__ext.annotations.apm_server_name", "operator": "=", "value": ["${service_name}"]}]
# 留空表示该业务下全部 APM 应用
APP_NAMES = []

set_request_username("admin")

SCOPE = {
    "bk_biz_id": BK_BIZ_ID,
    "is_global": True,
    "log_type": ServiceRelationLogTypeChoices.BK_LOG,
    "related_bk_biz_id": RELATED_BK_BIZ_ID,
}
# service_name 参与唯一键比对，sync_relations 只会自动补 bk_biz_id 和 app_name
RECORD = {**SCOPE, "service_name": "", "value": "", "addition": ADDITION}

# value_list 必须是 int；排序消除顺序抖动，避免重复执行被判定为有差异
index_set_ids = sorted(int(index_set_id) for index_set_id in INDEX_SET_IDS)

app_names = APP_NAMES or list(Application.objects.filter(bk_biz_id=BK_BIZ_ID).values_list("app_name", flat=True))

# 该唯一键没有 DB 约束，一次性取出并校验重复
relations = list(LogServiceRelation.objects.filter(**SCOPE, app_name__in=app_names).order_by("id"))
existing = {relation.app_name: relation for relation in relations}
assert len(relations) == len(existing), f"存在重复全局配置：{[relation.id for relation in relations]}"

for app_name in app_names:
    relation = existing.get(app_name)
    # sync_relations 是覆盖语义，存量索引集先取并集再提交
    exists = relation.value_list if relation else []
    value_list = sorted({int(value) for value in exists} | set(index_set_ids))
    result = LogServiceRelation.sync_relations(
        bk_biz_id=BK_BIZ_ID,
        app_name=app_name,
        records=[{**RECORD, "value_list": value_list}],
        scope=SyncScope.GLOBAL,
        is_delete=False,
    )
    print(app_name, value_list, result)

# addition 不在 DEFAULT_KEYS 中，sync_relations 只在新建时写入，存量记录统一补一次
print("addition", LogServiceRelation.objects.filter(**SCOPE, app_name__in=app_names).update(addition=ADDITION))
```

**写入语义**

- `LogServiceRelation.DEFAULT_KEYS` 只有 `value` 和 `value_list`，`addition` 不参与 diff，`sync_relations` 仅在新建记录时写入。
- 存量记录的过滤条件靠末尾那次 `update` 补齐，这是覆盖写，会抹掉脚本之外手工添加的过滤字段。
- `scope=SyncScope.GLOBAL` 配 `is_delete=False` 只做增改，同应用下关联其他业务的全局记录不受影响。

**生效条件**

- `addition` 使用日志平台格式 `field / operator / value`，不是监控条件的 `key / method / value / condition`。
- `${service_name}` 只在带服务名查询时替换并挂上，应用级查询只返回索引集，不加过滤。
- 从 Span / Trace 详情进入日志时，`addition` 被 `span_id` / `trace_id` 的精确过滤整体覆盖。
- 关联结果有 `5` 分钟缓存，写库后页面不会立即变化。

### d. 按命名规则导入容器关联

按应用遍历已上报服务，用服务名规范化规则匹配 `trpc-*` 命名空间的 Deployment，再按应用调用 `EventServiceRelation.sync_relations` 写入 `k8s_event`。

```python
import re
from collections import defaultdict

from apm_web.constants import SyncScope
from apm_web.models import Application, EventServiceRelation
from apm_web.strategy.dispatch.entity import EntitySet
from bkmonitor.models import BCSWorkload
from bkmonitor.utils.request import set_request_username
from monitor_web.data_explorer.event.constants import EventCategory

BK_BIZ_ID = 150
DRY_RUN = True
APP_NAMES: list[str] = []  # 空=全量

set_request_username("admin")

ENV_RE = re.compile(r"^(?P<s>.+)\.(?:test|production|development|prod|dev|gz)\.\d+\.deploy$", re.I)
PLAIN_RE = re.compile(r"^(?P<s>.+)\.deploy$", re.I)

def stem(name: str) -> str:
    m = ENV_RE.match(name) or PLAIN_RE.match(name)
    return m.group("s").lower() if m else ""

def norm(svc: str) -> str:
    return re.sub(r"\s+", "", svc.strip()).replace("_", "").lower()

wl_map: dict[str, list[dict]] = defaultdict(list)
for w in BCSWorkload.objects.filter(
    bk_biz_id=BK_BIZ_ID, type="Deployment", namespace__startswith="trpc-",
    name__endswith=".deploy", deleted_at__isnull=True,
).values("bcs_cluster_id", "namespace", "type", "name"):
    s = stem(w["name"])
    if s:
        wl_map[s].append({"bcs_cluster_id": w["bcs_cluster_id"], "namespace": w["namespace"],
                          "kind": w["type"], "name": w["name"]})

apps = APP_NAMES or list(Application.objects.filter(bk_biz_id=BK_BIZ_ID).values_list("app_name", flat=True))
for app_name in apps:
    records: list[dict] = []
    for svc in EntitySet(BK_BIZ_ID, app_name).service_names:
        n = norm(svc)
        stems = {n, n + "cgi"}
        if n.count(".") >= 3:
            stems.add(".".join(n.split(".")[1:]))
        rels, seen = [], set()
        for st in stems:
            for w in wl_map.get(st, []):
                key = (w["bcs_cluster_id"], w["namespace"], w["name"])
                if key not in seen:
                    seen.add(key)
                    rels.append(w)
        if rels:
            records.append({"service_name": svc, "is_global": False, "table": EventCategory.K8S_EVENT.value,
                            "relations": rels, "options": {}})
    if not records:
        print(app_name, "skip")
        continue
    if DRY_RUN:
        print(app_name, "dry", len(records), sum(len(r["relations"]) for r in records))
        continue
    print(app_name, EventServiceRelation.sync_relations(
        bk_biz_id=BK_BIZ_ID, app_name=app_name, records=records,
        scope=SyncScope.ALL, is_delete=True, table=EventCategory.K8S_EVENT.value,
    ))
```

- 匹配规则：`stem = lower(去空白 / 下划线)`，对齐 `{stem}.deploy` 或 `{stem}.{env}.{setid}.deploy`，并补 `{stem}cgi`；服务名超过 `3` 段点号才丢掉第一段。
- 正式环境 namespace 为 `trpc-{cgi|svr|html}-prod`，脚本不过滤环境，test / prod / dev 一并写入。
- 先看 `dry` 输出，再把 `DRY_RUN` 改成 `False` 落库。
- `is_delete=True` 不删除 `system_event` 和其他关联。
