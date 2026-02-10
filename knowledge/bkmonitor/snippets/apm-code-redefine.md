---
title: APM 返回码重定义
tags: [apm, code-redefine, error-code]
description: 批量设置 APM 服务返回码重定义规则
language: python
created: 2026-02-09
updated: 2026-02-09
---

# APM 返回码重定义

## 0x01 关键信息

### a. 适用场景

批量为 APM 应用的所有服务设置返回码重定义规则，将特定返回码映射为成功/超时/异常。

## 0x02 代码片段

### a. 批量设置返回码重定义

```python
from typing import Any
from apm_web.strategy.dispatch.entity import EntitySet
from apm_web.models.service import CodeRedefinedConfigRelation
from apm_web.service.resources import SetCodeRedefinedRuleResource

bk_biz_id: int = 5016858
app_name: str = "tf_test"

# 格式：单个码用逗号分隔，范围用波浪线连接
rules: dict[str, str] = {
    "success": "409,10001~10002,10006,10008~10009,11002~11003,11005,11007,11100~11199,11215,11300~11301,11450~11499,11501,11503,11601~11618,11701~11703,11802,11901~11905,11907~11909,11913~11916,11919~11920,11924,15202~15206,15208~15212,15214~15215,13004",
    "timeout": "",
    "exception": ""
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
        "code_type_rules": rules
    }
    relations.append(CodeRedefinedConfigRelation(kind="callee", **params))
    relations.append(CodeRedefinedConfigRelation(kind="caller", **params))

CodeRedefinedConfigRelation.objects.bulk_create(relations)

# 构建并发布配置
SetCodeRedefinedRuleResource.build_code_relabel_config(bk_biz_id, app_name)
SetCodeRedefinedRuleResource.publish_code_relabel_to_apm(bk_biz_id, app_name)
```
