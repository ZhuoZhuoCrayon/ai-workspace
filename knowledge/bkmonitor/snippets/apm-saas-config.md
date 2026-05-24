---
title: APM SaaS 配置
tags: [apm, saas-config, code-redefine, log-relation, django-shell]
description: 记录 APM SaaS 侧返回码重定义与服务关联日志配置脚本
language: python
created: 2026-02-09
updated: 2026-05-24
---

# APM SaaS 配置

## 0x01 关键信息

### a. 适用场景

在 Django shell 中批量维护 APM SaaS 配置，包括返回码重定义规则和服务关联日志规则。

### b. 使用边界

- 返回码重定义写库后，需要重新构建并发布 APM 配置。
- 服务关联日志脚本使用 `scope=SyncScope.ALL` 和 `is_delete=True`，适合确认脚本已包含应用全量规则的场景。
- `LogServiceRelation.value_list` 必须使用 `int` 类型，避免后续按索引集过滤时匹配失败。

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
