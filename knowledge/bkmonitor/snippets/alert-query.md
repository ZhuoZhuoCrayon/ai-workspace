---
title: 告警查询与处理
tags: [alert, alarm, fta]
description: 告警相关的查询、屏蔽、通知等代码片段
language: python
created: 2026-02-09
updated: 2026-02-09
---

# 告警查询与处理

## 0x01 关键信息

### a. 适用场景

告警排查、告警通知模板调试、告警屏蔽规则验证等场景。

## 0x02 代码片段

### a. 查询告警并获取上下文

```python
from core.drf_resource import api
from bkmonitor.documents import AlertDocument
from alarm_backends.core.alert import Alert
from alarm_backends.service.alert.enricher.kubernetes_cmdb import KubernetesCMDBEnricher

alert_ids = ["1708665229279586455"]
alerts = []
for alert_id in alert_ids:  
    alert = Alert(AlertDocument.get(alert_id).to_dict())
    alert._is_new = True
    alerts.append(alert)

k8s_enricher = KubernetesCMDBEnricher(alerts)

alert = k8s_enricher.alerts[0]
source_info = alert.get_origin_alarm_dimensions()
api.unify_query.get_kubernetes_relation({"bk_biz_ids": [alert.bk_biz_id], "source_info_list": [source_info]})
```

### b. 获取告警通知上下文

```python
from core.drf_resource import api
from bkmonitor.documents import AlertDocument
from alarm_backends.core.alert import Alert
from bkmonitor.models.fta import ActionInstance
from alarm_backends.core.context import ActionContext

strategy_id = 10563
alert_id = "17625711727532664"

alert = AlertDocument.get(alert_id)
action = ActionInstance.objects.filter(strategy_id=strategy_id).last()

context = ActionContext(action, alerts=[alert]).get_dictionary()
```

### c. 验证告警屏蔽规则

```python
from bkmonitor.models.base import Shield  
from alarm_backends.service.converge.shield.shield_obj import AlertShieldObj

ids = [19465, 206575, 299292, 312710, 335732, 335771]
configs = list(Shield.objects.filter(id__in=ids).values())

for config in configs:  
    shield_obj = AlertShieldObj(config)  
    if shield_obj.dimension_check.is_match(shield_obj.get_dimension(alert)):  
        print(1)
```

### d. 告警查询 DSL 转换

```python
from core.drf_resource import resource
from fta_web.alert.handlers.alert import AlertQueryHandler

show_overview = validated_request_data.pop("show_overview", False)
show_aggs = validated_request_data.pop("show_aggs", True)
show_dsl = validated_request_data.pop("show_dsl", False)
record_history = validated_request_data.pop("record_history", True)

handler = AlertQueryHandler(**validated_request_data)
handler.query_transformer.transform_query_string(validated_request_data["query_string"])
```

### e. 发送告警通知

```python
from core.drf_resource import api
from bkmonitor.documents import AlertDocument
from bkmonitor.utils.send import Sender
from alarm_backends.core.alert import Alert
from bkmonitor.models.fta import ActionInstance
from alarm_backends.core.context import ActionContext
from alarm_backends.service.alert.enricher.dimension import MonitorTranslateEnricher

# RPC 主调成功率
strategy_id = 10703
alert_id = "17627799527553782"

alert = AlertDocument.get(alert_id)
MonitorTranslateEnricher([]).enrich_alert(Alert(alert.to_dict()))

notice_way = "wxwork-bot"
action = ActionInstance.objects.filter(strategy_id=strategy_id).last()
context = ActionContext(action, alerts=[alert], notice_way=notice_way).get_dictionary()

wx_group_id = "fixme:企业微信群 ID"
content_template_path = "notice/abnormal/action/markdown_content.jinja"
title_template_path = f"notice/abnormal/action/{notice_way}_title.jinja"
sender = Sender(context, content_template_path=content_template_path, title_template_path=title_template_path)
sender.send(notice_way, notice_receivers=[wx_group_id])
```

### f. 自愈动作查询

```python
from bkmonitor.models import ActionInstance

strategy_id = 8200

action_instance = ActionInstance.objects.filter(strategy_id=strategy_id).first()
action_instance.action_config
```
