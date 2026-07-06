---
title: APM Trace 写入 ES 字段类型冲突
tags: [apm, trace, elasticsearch, mapping, attribute-filter, normaltypevalueconfig]
description: APM Trace 属性同时上报 upstream_cluster 和 upstream_cluster.name，触发 ES keyword 与 object mapping 冲突，可通过应用级 attribute_filter drop 配置止血
created: 2026-07-02
updated: 2026-07-02
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

在 bkmonitor SaaS 的 django shell 中执行。脚本只追加应用级 `db_config.drop` 规则，并用
`need_delete_config=False` 保留同应用的其他配置。

```python
import json

from apm.constants import ConfigTypes
from apm.models import AppConfigBase, NormalTypeValueConfig
from apm.task.tasks import refresh_apm_application_config

BK_BIZ_ID = -4258012
APP_NAME = "nba2kol3"
DROP_FIELD = "attributes.upstream_cluster.name"

query = {
    "bk_biz_id": BK_BIZ_ID,
    "app_name": APP_NAME,
    "config_level": AppConfigBase.APP_LEVEL,
    "config_key": APP_NAME,
    "type": ConfigTypes.DB_CONFIG,
}
config = NormalTypeValueConfig.objects.filter(**query).first()
value = json.loads(config.value) if config and config.value else {}
drop_rules = value.setdefault("drop", [])
if not isinstance(drop_rules, list):
    raise ValueError("db_config.drop must be a list")

rule = {"predicate_key": DROP_FIELD, "keys": [DROP_FIELD]}
if rule not in drop_rules:
    drop_rules.append(rule)
    NormalTypeValueConfig.refresh_config(
        BK_BIZ_ID,
        APP_NAME,
        AppConfigBase.APP_LEVEL,
        APP_NAME,
        [{"type": ConfigTypes.DB_CONFIG, "value": json.dumps(value, ensure_ascii=False)}],
        need_delete_config=False,
    )

refresh_apm_application_config.delay(BK_BIZ_ID, APP_NAME)
print(json.dumps(value, ensure_ascii=False, indent=2))
```
