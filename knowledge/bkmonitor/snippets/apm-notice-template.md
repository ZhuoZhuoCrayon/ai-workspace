---
title: APM 告警通知模板
tags: [apm, alert, notice, template, jinja]
description: APM 告警通知模板渲染和发送测试
language: python
created: 2026-02-09
updated: 2026-02-09
---

# APM 告警通知模板

## 0x01 关键信息

### a. 适用场景

调试和测试告警通知模板渲染效果，验证通知发送。

## 0x02 代码片段

### a. 基础通知模板测试

```python
import time
from elasticsearch_dsl import AttrDict
from alarm_backends.core.context import ActionContext
from bkmonitor.utils.send import Sender
from bkmonitor.models.fta.action import ActionInstance
from bkmonitor.documents import AlertLog, EventDocument
from constants.alert import EventSeverity, EventStatus
from constants.action import ActionPluginType, ActionStatus, NoticeWay
from packages.fta_web.action.resources import AlertDocument

current_time = int(time.time())
event = EventDocument(**{
    "bk_biz_id": 2,
    "ip": "127.0.0.1",
    "time": int(time.time()),
    "create_time": int(time.time()),
    "bk_cloud_id": 0,
    "id": 123,
})

alert_info = {
    "id": "1",
    "alert_name": "test",
    "event": event,
    "severity": 1,
    "dedupe_md5": "68e9f0598d72a4b6de2675d491e5b922",
    "begin_time": int(time.time()),
    "create_time": int(time.time()),
    "latest_time": current_time,
    "first_anomaly_time": current_time,
    "duration": 60,
    "common_dimensions": {},
    "dimensions": [
        AttrDict({"key": "tags.backend", "value": "test_tags", "display_key": "backend", "display_value": "1"}),
        AttrDict({"key": "bk_target_ip", "value": "127.0.0.1", "display_key": "主机IP", "display_value": "127.0.0.1"}),
        AttrDict({"key": "bk_target_cloud_id", "value": "2", "display_key": "云区域ID", "display_value": "2"}),
    ],
    "extra_info": {"strategy": {}, "agg_dimensions": ["bk_target_cloud_id", "bk_target_ip"]},
    "status": EventStatus.ABNORMAL,
}

alert = AlertDocument(**alert_info)
action = ActionInstance.objects.create(
    alerts=[alert.id],
    signal="abnormal",
    strategy_id=0,
    alert_level=alert.severity,
    status=ActionStatus.SUCCESS,
    bk_biz_id=2,
    inputs={},
    action_config={},
    action_config_id=0,
    action_plugin={
        "plugin_type": ActionPluginType.NOTICE,
        "name": "通知",
        "plugin_key": ActionPluginType.NOTICE,
    },
)

context = ActionContext(
    action=action, alerts=[alert], use_alert_snap=True, notice_way=NoticeWay.WX_BOT
).get_dictionary()

content_template_path = "notice/abnormal/action/wxwork-bot_layouts.jinja"
sender = Sender(context, content_template_path=content_template_path)
sender.send("wxwork-bot", notice_receivers=["wrkSFfCgAA4GGgUmb5QQ7DVG1jsftIeg"])
```

### b. Taf/tRPC 告警模板测试

```python
import time
from elasticsearch_dsl import AttrDict
from alarm_backends.core.context import ActionContext
from bkmonitor.utils.send import Sender
from bkmonitor.models import StrategyModel
from bkmonitor.models.fta.action import ActionInstance
from bkmonitor.strategy.new_strategy import Strategy
from bkmonitor.documents import EventDocument
from constants.alert import EventStatus
from constants.action import ActionPluginType, ActionStatus, NoticeWay
from packages.fta_web.action.resources import AlertDocument

current_time = int(time.time())
event = EventDocument(**{
    "category": "apm",
    "bk_biz_id": 2,
    "time": int(time.time()),
    "create_time": int(time.time()),
    "description": "[调用分析] 主调成功率（%） <= 99.0, 当前值95.833333"
})

dimensions = {
    "app_name": None,
    "service_name": "TestApp.HelloGo",
    "namespace": None,
    "env_name": None,
    "callee_method": "Sub"
}
origin_alarm = {"data": {"dimensions": dimensions}}
agg_dimensions = ["app_name", "service_name", "namespace", "env_name", "callee_method"]
strategy = Strategy.from_models(StrategyModel.objects.filter(id=278))[0]

alert_info = {
    "id": "1",
    "alert_name": "[调用分析] 被调成功率告警 [bcs_k8s_40735_defaul/TestApp.HelloGo]",
    "event": event,
    "severity": 1,
    "dedupe_md5": "cfec8c322dfbe74fa5a0e7dab2bf99f4",
    "begin_time": int(time.time()),
    "create_time": int(time.time()),
    "latest_time": current_time,
    "first_anomaly_time": current_time,
    "duration": 60,
    "common_dimensions": {},
    "strategy": strategy,
    "dimensions": [
        AttrDict({
            "key": f"tags.{k}", "value": dimensions[k], 
            "display_key": k, "display_value": dimensions[k]
        })
        for k in agg_dimensions
    ],
    "extra_info": {"strategy": strategy, "agg_dimensions": agg_dimensions, "origin_alarm": origin_alarm},
    "status": EventStatus.ABNORMAL,
}

alert = AlertDocument(**alert_info)
action = ActionInstance.objects.create(
    alerts=[alert.id],
    signal="abnormal",
    strategy_id=0,
    alert_level=alert.severity,
    status=ActionStatus.SUCCESS,
    bk_biz_id=2,
    inputs={},
    action_config={},
    action_config_id=0,
    action_plugin={"plugin_type": ActionPluginType.NOTICE, "name": "通知", "plugin_key": ActionPluginType.NOTICE},
)

# 企业微信群 ID
wx_group_id = "fixme:企业微信群 ID"
context = ActionContext(
    action=action, alerts=[alert], use_alert_snap=True, notice_way=NoticeWay.WX_BOT
).get_dictionary()
context["mentioned_users"] = {wx_group_id: ["fixme:英文名"]}

content_template_path = "notice/abnormal/action/wxwork-bot_layouts.jinja"
sender = Sender(context, content_template_path=content_template_path)
sender.send("wxwork-bot", notice_receivers=[wx_group_id])
```
