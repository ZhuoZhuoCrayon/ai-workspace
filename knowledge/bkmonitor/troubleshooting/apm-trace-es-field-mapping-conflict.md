---
title: APM Trace 写入 ES 字段类型冲突
tags: [apm, trace, elasticsearch, mapping, attribute-filter, as-string, index-rollover, normaltypevalueconfig, all-app-config]
description: APM Trace 字段在 keyword/object 或 long/string 之间冲突时的定位与修复方法，覆盖独立 drop 止血、APP 全量配置和 APM_GLOBAL 配合索引轮转的类型迁移
created: 2026-07-02
updated: 2026-07-19
---

# APM Trace 写入 ES 字段类型冲突

## 0x01 关键信息

### a. 现象

APM Trace 写入 Elasticsearch 失败，日志中出现同类错误：

```text
backend elasticsearch/space_2_bkapm.trace_bkop write 68 documents to elasticsearch failed
mapper [attributes.upstream_cluster] cannot be changed from type [keyword] to [ObjectMapper]
can't merge a non object mapping [attributes.upstream_cluster] with an object mapping
```

失败批次中的样例同时包含两个属性：

```json
{
  "attributes": {
    "upstream_cluster": "PassthroughCluster",
    "upstream_cluster.name": "PassthroughCluster"
  }
}
```

### b. 根因

样例里的 `upstream_cluster` 本身是字符串。真正的问题是 `upstream_cluster.name` 这个带点号的属性名。

Elasticsearch 会把带点号字段展开成对象路径。写入侧等价于同时提交：

```json
{
  "attributes": {
    "upstream_cluster": "PassthroughCluster"
  }
}
```

和：

```json
{
  "attributes": {
    "upstream_cluster": {
      "name": "PassthroughCluster"
    }
  }
}
```

同一个字段不能同时是 `keyword` 和 `object`。旧索引里 `attributes.upstream_cluster` 已经是 `keyword` 后，后续再写入
`attributes.upstream_cluster.name` 就会触发 mapping 合并失败。

## 0x02 排查过程

这一节依赖两个输入：APM 应用名 `APP_NAME` 和 Trace 写入业务 ID `TRACE_BIZ_ID`。`TRACE_BIZ_ID` 使用索引里的数字形式；如果业务 ID 是负数，先去掉负号。时间窗口按故障发生时间取，先查 `6` 小时；命中太少再放宽到 `24` 小时。

### a. 查 transfer 写入失败日志

transfer 写入 ES 失败日志在 bkop 业务 `7`、索引集 `553`。一次查询同时覆盖应用名和两种 Trace 写入索引名：

```json
{
  "tool": "mcp__bkm_bkop_log_query.search_logs",
  "arguments": {
    "body_param": {
      "bk_biz_id": "7",
      "index_set_id": "553",
      "query_string": "(\"<APP_NAME>\" OR \"space_<TRACE_BIZ_ID>_bkapm.trace_<APP_NAME>\" OR \"<TRACE_BIZ_ID>_bkapm.trace_<APP_NAME>\") AND \"documents to elasticsearch failed\"",
      "start_time": "<now - 6h 的秒级时间戳>",
      "end_time": "<now 的秒级时间戳>",
      "limit": "20"
    }
  }
}
```

如果结果太多，再追加通用 ES mapping 关键词，例如 `"mapper ["`、`"can't merge"` 或 `"cannot be changed from type"`。

### b. 读取日志结论

命中日志后，先看原始 message，再记录这几项：

| 字段 | 用途 |
| --- | --- |
| `dtEventTimeStamp` | 作为拉上下文的中心时间 |
| `serverIp` / `container_id` | 限定同一个 transfer 实例 |
| `gseIndex` / `gseindex` | 定位同一批日志 |
| 原始 message | 读取写入索引、失败文档数量和 ES 报错原文 |

判断字段冲突时，不要预设具体字段名。以 message 里的 `mapper [...]`、`can't merge ... mapping` 或
`cannot be changed from type [...]` 为准，再回到失败样例确认是哪一组属性触发冲突。

## 0x03 解决方案

从 `ff67e91d57` 开始，`ConfigTypes.DROP_FIELDS_CONFIG` 的值是完整的 drop 规则数组。系统生成应用配置时，会将
这些规则与 `DB_CONFIG.drop` 合并，并按规则内容去重。

`DROP_FIELDS_CONFIG` 是独立配置。页面更新 `DB_CONFIG` 时不会覆盖它。

### a. 通过 Admin 配置

进入 Django Admin 的 `Normal type value config`，为目标应用新增一条配置：

| 字段 | 配置值 |
| --- | --- |
| 业务 ID | `2` |
| 应用名称 | `bkop` |
| 配置级别 | `app_level` |
| 配置 KEY | `bkop` |
| 配置类型 | `后台 drop 字段配置（drop_fields_config）` |

配置值：

```json
[
  {
    "predicate_key": "attributes.istio.mesh_id",
    "match": ["bcs-mesh-48rpf4on"],
    "keys": ["attributes.upstream_cluster.name"]
  }
]
```

该规则的语义是：当 `attributes.istio.mesh_id` 等于 `bcs-mesh-48rpf4on` 时，删除 `attributes.upstream_cluster.name`。

不要修改已有的 `db配置（db_config）` 记录。`drop_fields_config` 的配置值直接使用规则数组，不要包成
`{"drop": [...]}`，也不要使用旧版的字段名字符串数组。

### b. 通过 Django shell 配置

无法使用 Admin 时，在 bkmonitor SaaS 的 Django shell 中执行：

```python
import json

from apm.constants import ConfigTypes
from apm.models import AppConfigBase, NormalTypeValueConfig

BK_BIZ_ID = 2
APP_NAME = "bkop"
DROP_RULES = [
    {
        "predicate_key": "attributes.istio.mesh_id",
        "match": ["bcs-mesh-48rpf4on"],
        "keys": ["attributes.upstream_cluster.name"],
    }
]

NormalTypeValueConfig.refresh_config(
    BK_BIZ_ID,
    APP_NAME,
    AppConfigBase.APP_LEVEL,
    APP_NAME,
    [
        {
            "type": ConfigTypes.DROP_FIELDS_CONFIG,
            "value": json.dumps(DROP_RULES, ensure_ascii=False),
        }
    ],
    need_delete_config=False,
)

print(
    NormalTypeValueConfig.get_app_value(
        BK_BIZ_ID,
        APP_NAME,
        ConfigTypes.DROP_FIELDS_CONFIG,
    )
)
```

`refresh_config()` 会按应用和配置类型新增或更新记录。`need_delete_config=False` 保留其他类型的配置；
`DROP_FIELDS_CONFIG` 的 `value` 仍按脚本内容整体覆盖。

### c. 验证配置生成

下面的脚本分别输出实时生成路径和定时批量下发缓存路径中的 drop 规则：

```python
import json

from apm.core.application_config import ApmConfigCache, ApplicationConfig
from apm.models import ApmApplication

BK_BIZ_ID = 2
APP_NAME = "bkop"

application = ApmApplication.objects.get(
    bk_biz_id=BK_BIZ_ID,
    app_name=APP_NAME,
)

# 配置新建或更新触发的生成路径
generated_config = ApplicationConfig(application).application_config

# 定时批量下发使用缓存的生成路径
cached_config = ApplicationConfig(application, ApmConfigCache()).application_config

print(json.dumps(generated_config["attribute_config"]["drop"], ensure_ascii=False, indent=2))
print(json.dumps(cached_config["attribute_config"]["drop"], ensure_ascii=False, indent=2))
```

两个输出都应包含页面维护的 DB drop 规则和后台规则。后台规则在每个数组中只能出现 `1` 次。

### d. 下发配置

确认生成结果后，触发应用配置下发：

```python
from apm.task.tasks import refresh_apm_application_config

refresh_apm_application_config.delay(BK_BIZ_ID, APP_NAME)
```

### e. 注意事项

- `DROP_FIELDS_CONFIG.value` 是整体覆盖。更新时必须保留仍需生效的旧规则。
- 配置只会阻止后续冲突字段写入，不会修改已有 ES Mapping。
- 下发后应确认 `attribute_config.drop` 包含新规则且只出现 `1` 次。
- 如果最终配置缺少新规则，检查全局 `ALL_APP_CONFIG` 是否覆盖了 `attribute_config.drop`。

## 0x04 将 long 字段迁移为 keyword

`attributes.trpc.status_type` 和 `attributes.trpc.status_code` 混合上报整数和字符串，旧索引已将它们映射为 `long`。

执行顺序：

1. 在 APP 全量配置中增加 `as_string`，并确认所有 Collector 实例已生效。
2. 强制轮转索引，让新索引将字符串映射为 `keyword`。

旧索引仍可在 Elasticsearch `coerce=true` 时接收 `"0"`、`"404"` 等数字字符串；非数字字符串会继续写入失败，直至索引
轮转完成。如果索引模板将目标字段固定为 `long`，必须先修改模板。

### a. 阶段 1：增加 as_string

```python
import json

from apm.constants import ConfigTypes
from apm.core.application_config import ApplicationConfig
from apm.models import ApmApplication, AppConfigBase, NormalTypeValueConfig
from apm.task.tasks import refresh_apm_application_config

APPS = [
    (5000140, "trpc_demo"),
]

KEYS = ["attributes.trpc.status_type", "attributes.trpc.status_code"]

for biz_id, app_name in APPS:
    raw = NormalTypeValueConfig.get_app_value(
        biz_id,
        app_name,
        ConfigTypes.ALL_APP_CONFIG,
    )
    config = json.loads(raw or "{}")

    attribute_config = config.setdefault("attribute_config", {})
    attribute_config.setdefault("name", "attribute_filter/app")
    attribute_config["as_string"] = list(
        dict.fromkeys(attribute_config.get("as_string", []) + KEYS)
    )

    NormalTypeValueConfig.refresh_config(
        biz_id,
        app_name,
        AppConfigBase.APP_LEVEL,
        app_name,
        [{
            "type": ConfigTypes.ALL_APP_CONFIG,
            "value": json.dumps(config, ensure_ascii=False),
        }],
        need_delete_config=False,
    )

    application = ApmApplication.objects.get(
        bk_biz_id=biz_id,
        app_name=app_name,
    )
    generated = ApplicationConfig(application).application_config

    print(
        biz_id,
        app_name,
        generated["attribute_config"]["as_string"],
    )

    refresh_apm_application_config.run(biz_id, app_name)
    print("下发成功")

print("全部配置更新并下发完成")
```

完成标志：所有 Collector 实例的应用配置都包含两个 `as_string` 字段。

### b. 阶段 2：轮转索引

确认第一阶段已全量生效后，批量创建新索引并切换写别名：

```python
from apm.models import ApmApplication, TraceDataSource
from metadata.models import ESStorage

APPS = [
    (5000140, "trpc_demo"),
]

for biz_id, app_name in APPS:
    application = ApmApplication.objects.get(
        bk_biz_id=biz_id,
        app_name=app_name,
    )
    trace = TraceDataSource.objects.get(
        bk_biz_id=biz_id,
        app_name=app_name,
    )
    storage = ESStorage.objects.get(
        table_id=trace.result_table_id,
        bk_tenant_id=application.bk_tenant_id,
    )

    print(biz_id, app_name, "before:", storage.current_index_info())
    if storage.update_index_v2(force_rotate=True) is False:
        raise RuntimeError(f"{biz_id}/{app_name}: 索引未启用，轮转失败")

    storage.create_or_update_aliases(force_rotate=True)
    print(biz_id, app_name, "after:", storage.current_index_info())
```

新数据写入后，检查目标字段的 Mapping 应为 `keyword`。旧索引仍是 `long`，跨新旧索引查询可能出现类型冲突，直至旧索引
过期或完成重建。

### c. 备选方案：写入 APM_GLOBAL

**（1）扫描现有配置**

先扫描全部 `NormalTypeValueConfig`，不限定应用和配置类型：

```python
import json

from apm.models import NormalTypeValueConfig


def find_as_string(value, path="$"):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key == "as_string":
                yield child_path, child
            yield from find_as_string(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from find_as_string(child, f"{path}[{index}]")


configs = NormalTypeValueConfig.objects.filter(
    value__contains='"as_string"'
).order_by("bk_biz_id", "app_name", "type")

for config in configs:
    matches = list(find_as_string(json.loads(config.value)))
    if not matches:
        continue

    print(
        f"id={config.id} biz={config.bk_biz_id} "
        f"app={config.app_name} type={config.type}"
    )
    for path, value in matches:
        print(f"  {path} = {json.dumps(value, ensure_ascii=False)}")
```

该脚本同时覆盖 `DB_CONFIG`、`ALL_APP_CONFIG` 和 `APM_GLOBAL` 中的 `as_string`。

**（2）更新 APM_GLOBAL**

需要对所有 APM 应用生效时，可以更新 `0 / APM_GLOBAL / ALL_APP_CONFIG`。脚本保留其他 Global 配置，替换同一
`source + destination` 的 replace 规则，并去重追加 `as_string`；重复执行结果不变。

```python
import json

from apm.constants import (
    APM_GLOBAL_CONFIG_KEY,
    GLOBAL_CONFIG_BK_BIZ_ID,
    ConfigTypes,
)
from apm.models import AppConfigBase, NormalTypeValueConfig

KEYS = ["attributes.trpc.status_type", "attributes.trpc.status_code"]
REPLACE = {
    "source": "telemetry.target",
    "destination": "service.name",
    "extract_pattern": r".*\.(.*\..*)",
}

raw = NormalTypeValueConfig.get_app_value(
    GLOBAL_CONFIG_BK_BIZ_ID,
    APM_GLOBAL_CONFIG_KEY,
    ConfigTypes.ALL_APP_CONFIG,
)
config = json.loads(raw or "{}")

resource_filter = config.setdefault("resource_filter_config", {})
replace_rules = resource_filter.setdefault("replace", [])
resource_filter["replace"] = [
    rule
    for rule in replace_rules
    if (
        rule.get("source"),
        rule.get("destination"),
    )
    != (
        REPLACE["source"],
        REPLACE["destination"],
    )
] + [REPLACE]

attribute = config.setdefault("attribute_config", {"name": "attribute_filter/app"})
attribute["as_string"] = list(
    dict.fromkeys(attribute.get("as_string", []) + KEYS)
)

NormalTypeValueConfig.refresh_config(
    GLOBAL_CONFIG_BK_BIZ_ID,
    APM_GLOBAL_CONFIG_KEY,
    AppConfigBase.APP_LEVEL,
    APM_GLOBAL_CONFIG_KEY,
    [{
        "type": ConfigTypes.ALL_APP_CONFIG,
        "value": json.dumps(config, ensure_ascii=False),
    }],
    need_delete_config=False,
)

print(json.dumps(config, ensure_ascii=False, indent=2))
```

`APM_GLOBAL` 的优先级低于应用自己的 APP 全量配置。应用如果单独配置了 `attribute_config` 或
`resource_filter_config`，会整体覆盖对应的 Global 配置。更新后需重新下发目标应用；确认生成结果包含目标规则后，再按
阶段 2 轮转索引。
