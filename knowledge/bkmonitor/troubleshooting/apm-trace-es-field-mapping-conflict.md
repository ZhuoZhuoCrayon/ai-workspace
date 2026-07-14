---
title: APM Trace 写入 ES 字段类型冲突
tags: [apm, trace, elasticsearch, mapping, attribute-filter, normaltypevalueconfig]
description: APM Trace 属性同时上报 upstream_cluster 和 upstream_cluster.name，触发 ES keyword 与 object mapping 冲突，可通过后台独立 drop 字段配置止血
created: 2026-07-02
updated: 2026-07-13
---

# APM Trace 写入 ES 字段类型冲突

## 0x01 关键信息

### a. 现象

APM Trace 写入 Elasticsearch 失败，日志中出现同类错误：

```text
backend elasticsearch/space_4258012_bkapm.trace_nba2kol3 write 68 documents to elasticsearch failed
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

后台 drop 字段使用独立的 `ConfigTypes.DROP_FIELDS_CONFIG` 存储。生成应用下发配置时，系统再将这些字段合并到
`attribute_config.drop`。该配置不会修改页面维护的 `DB_CONFIG`，页面查看和更新 DB 配置时也不会覆盖它。

### a. 新增或更新后台配置

在 bkmonitor SaaS 的 Django shell 中执行：

```python
import json

from apm.constants import ConfigTypes
from apm.models import AppConfigBase, NormalTypeValueConfig

BK_BIZ_ID = -4258012
APP_NAME = "nba2kol3"
DROP_FIELDS = ["attributes.upstream_cluster.name"]

NormalTypeValueConfig.refresh_config(
    BK_BIZ_ID,
    APP_NAME,
    AppConfigBase.APP_LEVEL,
    APP_NAME,
    [
        {
            "type": ConfigTypes.DROP_FIELDS_CONFIG,
            "value": json.dumps(DROP_FIELDS, ensure_ascii=False),
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

### b. 验证配置生成

下面的脚本分别检查实时生成路径和定时批量下发使用的缓存路径。

输出的 `attribute_config.drop` 应同时包含页面维护的 DB drop 规则和 `attributes.upstream_cluster.name`：

```python
import json

from apm.core.application_config import ApmConfigCache, ApplicationConfig
from apm.models import ApmApplication

BK_BIZ_ID = -4258012
APP_NAME = "nba2kol3"
DROP_FIELD = "attributes.upstream_cluster.name"

expected_rule = {
    "predicate_key": DROP_FIELD,
    "keys": [DROP_FIELD],
}

application = ApmApplication.objects.get(
    bk_biz_id=BK_BIZ_ID,
    app_name=APP_NAME,
)


def print_result(scene, generated_config):
    attribute_config = generated_config.get("attribute_config", {})
    drop_rules = attribute_config.get("drop", [])

    print(f"\n--- {scene} ---")
    print("后台规则已合并:", expected_rule in drop_rules)
    print("后台规则数量:", drop_rules.count(expected_rule))
    print(json.dumps(attribute_config, ensure_ascii=False, indent=2))


generated_config = ApplicationConfig(application).application_config
print_result("实时配置生成", generated_config)

config_cache = ApmConfigCache()
cached_config = ApplicationConfig(application, config_cache).application_config
print_result("定时缓存配置生成", cached_config)
```

### c. 下发配置

确认生成结果后，触发应用配置下发：

```python
from apm.task.tasks import refresh_apm_application_config

refresh_apm_application_config.delay(BK_BIZ_ID, APP_NAME)
```
