---
title: APM Trace 写入 ES 字段类型冲突
tags: [apm, trace, elasticsearch, mapping, attribute-filter, as-string, index-rollover, normaltypevalueconfig]
description: APM Trace 字段在 keyword/object 或 long/string 之间冲突时的定位与修复方法，覆盖独立 drop 止血和 as_string 配合索引轮转的类型迁移
created: 2026-07-02
updated: 2026-07-17
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

`attributes.trpc.status_type` 和 `attributes.trpc.status_code` 可能同时上报整数和字符串。Collector 固定先执行
`as_string`，再执行 drop，YAML 中的配置顺序不会改变处理顺序。为避免转换后的字符串写入旧的 `long` 索引，
迁移过程先单独启用无条件 drop，索引轮转完成后再将 drop 替换为 `as_string`。

以下脚本以业务 `5000140`、应用 `trpc_demo` 为例。`refresh_apm_application_config.run()` 同步执行配置下发，不使用
异步任务。

### a. 配置临时 drop

第一阶段移除目标字段已有的 `as_string`，再配置无条件 drop。`match: []` 表示字段存在时直接删除，确保索引轮转前
不会写入这两个字段。脚本兼容曾经误写的 `{"keys": [...]}` 结构及其渲染产物 `["keys"]`，重复执行会得到相同结果。

```python
import json

from apm.constants import ConfigTypes
from apm.models import AppConfigBase, NormalTypeValueConfig
from apm.task.tasks import refresh_apm_application_config

BIZ, APP = 5000140, "trpc_demo"
KEYS = ["attributes.trpc.status_type", "attributes.trpc.status_code"]

raw = NormalTypeValueConfig.get_app_value(BIZ, APP, ConfigTypes.DB_CONFIG)
config = json.loads(raw or "{}")

as_string = config.get("as_string", [])
as_string = as_string.get("keys", []) if isinstance(as_string, dict) else as_string
config["as_string"] = [key for key in as_string if key != "keys" and key not in KEYS]

config["drop"] = [
    rule for rule in config.get("drop", []) if not set(rule.get("keys", [])) & set(KEYS)
]
config["drop"] += [{"predicate_key": key, "match": [], "keys": [key]} for key in KEYS]

NormalTypeValueConfig.refresh_config(
    BIZ,
    APP,
    AppConfigBase.APP_LEVEL,
    APP,
    [{"type": ConfigTypes.DB_CONFIG, "value": json.dumps(config)}],
    need_delete_config=False,
)
refresh_apm_application_config.run(BIZ, APP)
```

执行后确认所有 Collector 实例都已加载新配置，再轮转索引。

### b. 强制轮转索引

强制轮转会创建新索引并切换别名，属于不可逆的外部操作。执行前必须确认第一阶段已在全部 Collector 实例生效。

```python
from apm.models import ApmApplication, TraceDataSource
from metadata.models import ESStorage

BIZ, APP = 5000140, "trpc_demo"

application = ApmApplication.objects.get(bk_biz_id=BIZ, app_name=APP)
trace = TraceDataSource.objects.get(bk_biz_id=BIZ, app_name=APP)
storage = ESStorage.objects.get(
    table_id=trace.result_table_id,
    bk_tenant_id=application.bk_tenant_id,
)

print("before:", storage.current_index_info())
if storage.update_index_v2(force_rotate=True) is False:
    raise RuntimeError("索引未启用，轮转失败")

storage.create_or_update_aliases(force_rotate=True)
print("after:", storage.current_index_info())
```

确认新索引已创建且写别名完成切换，再解除临时 drop。

### c. 将 drop 替换为 as_string

第三阶段在同一次配置更新中删除临时 drop，并增加 `as_string`。尚未更新的 Collector 继续删除字段；已更新的
Collector 将字段转换为字符串后写入新索引。`DB_CONFIG.as_string` 使用字段数组，配置模板会为它补上 `keys`；
不要在数据库中写成 `{"keys": [...]}`。`DROP_FIELDS_CONFIG` 不存放这两个 tRPC 状态字段的规则，不需要修改。

```python
import json

from apm.constants import ConfigTypes
from apm.models import AppConfigBase, NormalTypeValueConfig
from apm.task.tasks import refresh_apm_application_config

BIZ, APP = 5000140, "trpc_demo"
KEYS = ["attributes.trpc.status_type", "attributes.trpc.status_code"]

raw = NormalTypeValueConfig.get_app_value(BIZ, APP, ConfigTypes.DB_CONFIG)
config = json.loads(raw or "{}")

config["drop"] = [
    rule for rule in config.get("drop", []) if not set(rule.get("keys", [])) & set(KEYS)
]
as_string = config.get("as_string", [])
as_string = as_string.get("keys", []) if isinstance(as_string, dict) else as_string
as_string = [key for key in as_string if key != "keys"]
config["as_string"] = list(dict.fromkeys(as_string + KEYS))

NormalTypeValueConfig.refresh_config(
    BIZ,
    APP,
    AppConfigBase.APP_LEVEL,
    APP,
    [{"type": ConfigTypes.DB_CONFIG, "value": json.dumps(config)}],
    need_delete_config=False,
)
refresh_apm_application_config.run(BIZ, APP)
```

迁移完成后，新写入的两个字段统一为字符串。检查新索引 Mapping 时，应看到对应字段为 `keyword`；如果索引模板
显式声明为 `long`，仅轮转索引无法改变字段类型，需要先修改模板。
