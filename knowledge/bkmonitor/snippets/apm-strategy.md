---
title: APM 策略
tags: [apm, strategy, trpc, tars, template, dispatch]
description: APM 策略模板管理、tRPC/Tars 策略应用等操作
language: python
created: 2026-02-09
updated: 2026-03-05
---

# APM 策略

## 0x01 关键信息

### a. 适用场景

- 为 tRPC/Tars 应用批量下发告警策略
- APM 策略模板的自动下发、手动注册、重置清理

---

## 0x02 tRPC 策略应用

### a. 策略应用命令

```shell
# 基础用法
python manage.py apply_rpc_strategies -b 2 -a "sandtrpc" -t "caller" "callee" -g 1 --caller-extra-group-by "callee_method" --callee-extra-group-by "callee_method"

# 带配置的用法
python manage.py apply_rpc_strategies -b 60 -a "trpc-oteam-sdk-access-demo" --config '{"caller": {"group_by": ["callee_method"]}, "callee": {"group_by": ["callee_method"]}}'

# 带过滤条件
python manage.py apply_rpc_strategies -b 2 -a "trpc-cluster-access-demo" -t "callee" "caller" "resource" "panic" --config '{"caller": {"group_by": ["callee_method"], "filter_dict": {"namespace__eq": "Development"}}, "callee": {"group_by": ["callee_method"], "filter_dict": {"namespace__eq": "Development"}}}'

# 指定服务
python manage.py apply_rpc_strategies -b 2 -a "trpc-cluster-access-demo" -g 997 -t "callee" "caller" "resource" -s "bkm.web" "bkm.product" --config '{"caller": {"group_by": ["callee_method"], "filter_dict": {"namespace__eq": "Development"}}, "callee": {"group_by": ["callee_method"], "filter_dict": {"namespace__eq": "Development"}}}'
```

### b. 上云环境示例

```shell
# 天天象棋
python manage.py apply_rpc_strategies -b 640 -a "qqchess" -g 83485 -t "callee" "caller" -s "qqchess.online_ai_svr" --config '{"caller": {"group_by": ["callee_method"], "filter_dict": {"namespace__eq": "Production"}}, "callee": {"group_by": ["callee_method"], "filter_dict": {"namespace__eq": "Production"}}}'

# Taf 服务批量
python manage.py apply_rpc_strategies -b 640 -a "qqchess" -g 84269 -t "callee" "caller" -s "QQChess.ActivitySvr" "QQChess.DailyRankServer" "QQChess.EventRouterServer" --config '{"caller": {"group_by": ["callee_method"]}, "callee": {"group_by": ["callee_method"]}}'

# 英雄杀小游戏
python manage.py apply_rpc_strategies -b 100380 -a "formal_thkgame_apm" -g 83494 -t "callee" "caller" --config '{"caller": {"group_by": ["callee_method"]}, "callee": {"group_by": ["callee_method"]}}'

# 和平精英周边生态
python manage.py apply_rpc_strategies -b -4228598 -a "hpjy-microservices-activities-production" -g 83239 83654 82538 -t "callee" "caller" --config '{"caller": {"group_by": ["callee_method"]}, "callee": {"group_by": ["callee_method"]}}'
```

### c. Python 代码调用

```python
from apm_web.handlers.metric_group import MetricHelper
from apm_web.handlers.strategy_group import (
    BaseStrategyGroup,
    GroupEnum,
    RPCApplyType,
    StrategyGroupRegistry,
)

bk_biz_id = 2
app_name = "trpc-cluster-access-demo"
apply_types = ["callee", "caller", "resource"]
notice_group_ids = [997]

metric_helper = MetricHelper(bk_biz_id, app_name)
group: BaseStrategyGroup = StrategyGroupRegistry.get(
    GroupEnum.RPC,
    bk_biz_id,
    app_name,
    metric_helper=metric_helper,
    notice_group_ids=notice_group_ids,
    apply_types=apply_types,
)
```

### d. 获取服务配置

```python
from apm_web.handlers import metric_group

bk_biz_id = 640
app_name = "qqchess"
service_name = "qqchess.PersonifyLinuxAiServer"

group: metric_group.TrpcMetricGroup = metric_group.MetricGroupRegistry.get(
    metric_group.GroupEnum.TRPC, bk_biz_id, app_name
)
group.get_server_config(server=service_name)
```

---

## 0x03 策略模板管理

### a. 模板自动下发

```python
from apm_web.strategy.handler import StrategyTemplateHandler

bk_biz_id: int = 2
app_name: str = "trpc-cluster-access-demo"
StrategyTemplateHandler.handle_auto_apply(bk_biz_id, app_name)

from apm_web.handlers import service_handler
nodes = service_handler.ServiceHandler.list_nodes(bk_biz_id, app_name)
```

### b. 模板注册

```python
from apm_web.models import Application
from apm_web.strategy.builtin.registry import BuiltinStrategyTemplateRegistry

BuiltinStrategyTemplateRegistry(Application.objects.get(bk_biz_id=2, app_name="trpc-cluster-access-demo")).register()
BuiltinStrategyTemplateRegistry(Application.objects.get(bk_biz_id=11, app_name="sand_local_dev")).register()
BuiltinStrategyTemplateRegistry(Application.objects.get(bk_biz_id=2, app_name="bkop")).register()
BuiltinStrategyTemplateRegistry(Application.objects.get(bk_biz_id=7, app_name="bkmonitor_production")).register()
BuiltinStrategyTemplateRegistry(Application.objects.get(bk_biz_id=2, app_name="bcs_k8s_40735_defaul")).register()
BuiltinStrategyTemplateRegistry(Application.objects.get(bk_biz_id=19062, app_name="esp_pubgm_prod")).register()
```

### c. 模板下发

```python
from apm_web.models import StrategyTemplate, StrategyInstance
from apm_web.strategy.dispatch.core import StrategyDispatcher
from apm_web.strategy.dispatch.base import DispatchExtraConfig
from apm_web.strategy.query_template import QueryTemplateWrapperFactory

strategy_template = StrategyTemplate.objects.get(id=1)
qtw = QueryTemplateWrapperFactory.get_wrapper(
    strategy_template.query_template["bk_biz_id"], strategy_template.query_template["name"]
)

dispatcher = StrategyDispatcher(strategy_template, qtw)
dispatcher.dispatch(
    ["bkm.web"], 
    extra_configs=[
        DispatchExtraConfig(
            service_name="bkm.web", 
            context={"ALARM_THRESHOLD_VALUE": 10}
        )
    ]
)
```

### d. 系统探测

```python
from apm_web.strategy.dispatch.enricher import SystemChecker
from apm_web.strategy.dispatch.entity import EntitySet

bk_biz_id = -4228598
app_name = "hpjy_microservices_activities"

e = EntitySet(bk_biz_id, app_name)
SystemChecker(e).check_systems()
```

### e. 重置清理

```python
from django.db.models import Q
from core.drf_resource import resource
from apm_web.models import StrategyTemplate, StrategyInstance

def clean_strategy_template_data(bk_biz_id: int, app_name: str | None = None) -> None:
    """清理策略模板相关数据"""
    q = Q(bk_biz_id=bk_biz_id)
    if app_name:
        q &= Q(app_name=app_name)

    strategy_instance_qs = StrategyInstance.objects.filter(q)
    resource.strategies.delete_strategy_v2({
        "bk_biz_id": bk_biz_id,
        "ids": list(strategy_instance_qs.values_list("strategy_id", flat=True))
    })
    strategy_instance_qs.delete()
    StrategyTemplate.origin_objects.filter(q).delete()
    
clean_strategy_template_data(2, "bkop")
clean_strategy_template_data(11, "sand_local_dev")
clean_strategy_template_data(2, "trpc-cluster-access-demo")
```

### f. 找出所有 tRPC 服务

```python
from apm_web.handlers import service_handler

bk_biz_id: int = 640
app_name: str = "qqchess"

for node in service_handler.ServiceHandler.list_nodes(bk_biz_id, app_name):
    try:
        if node["system"][0]["extra_data"]["rpc_system"] == "tars":
            continue
    except Exception:
        pass
    print('"' + node["topo_key"] + '",')
```
