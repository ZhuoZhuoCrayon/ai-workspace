---
title: 外部版授权
tags: [external, auth, permission, grafana]
description: 外部版项目空间授权配置
language: python
created: 2026-02-09
updated: 2026-02-09
---

# 外部版授权

## 0x01 关键信息

### a. 适用场景

为外部用户配置项目空间访问权限，主要用于外部版 Grafana 仪表盘访问。

### b. 相关链接

- 授权入口：`<BKTE_BKMONITOR_URL>/?bizId=-4220213#/external-auth`
- 外部访问：`https://bkm.po.tencent.com/external/`

## 0x02 代码片段

### a. 配置项目授权人并创建权限

```python
from typing import Any
from monitor.models import GlobalConfig
from monitor_web.iam.resources import create_permission

bk_biz_id: int = -4227107

# 增加项目授权人
authorizer_map, _ = GlobalConfig.objects.get_or_create(
    key="EXTERNAL_AUTHORIZER_MAP", 
    defaults={"value": {}}
)
authorizer_map.value[str(bk_biz_id)] = "rtx"
authorizer_map.save()

# 创建权限
params: dict[str, Any] = {
    "action_id": "view_grafana",
    "bk_biz_id": -4227107,
    # 来源：<BKTE_BKMONITOR_URL>/rest/v2/external/get_resource_by_action/?bk_biz_id=-4227107&action_id=view_grafana
    "resources": [
        "WOMyZdfSk",
        "bT8qy3NVz",
        "bT8qy3NVa",
        "af39mwhy5cnpcc",
        "df3dpb18r00zke",
        "0n7euhwj34jl",
        "ml1i5qsyuiwj",
        "ff39nkj1hiuiod",
        "cf7ybllytibk0d",
        "ff7iufcakhudce"
    ],
    "expire_time": "2026-10-31T23:59:59+08:00"
}

create_permission(["fixme:英文名"], params)
```
