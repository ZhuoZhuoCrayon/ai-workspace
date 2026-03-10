---
title: 服务关联索引集在日志检索页面部分缺失
tags: [apm, log-relation, index-set, bug]
description: 服务配置多个索引集后，日志检索页面只展示其中一个，根因是 process_service_relation 中 next() 只取首个匹配
created: 2026-03-10
updated: 2026-03-10
---

# 服务关联索引集在日志检索页面部分缺失

## 0x01 关键信息

### a. 现象

- 服务配置（`LogServiceRelation`）关联了两个索引集。
- 接口（`ServiceRelationListResource`）只返回其中一个。

### b. 根因

`apm_web.log.resources.process_service_relation` 对每条 `LogServiceRelation` 使用 `next()` 匹配索引，只取**第一个**命中项，`value_list` 中的后续 ID 被静默丢弃。

## 0x02 排查过程

写入侧 `ServiceConfigResource.update_log_relations` 按 `related_bk_biz_id` 合并，同业务的多个索引集存为一条记录（`value_list=[101, 102]`）。

查询链路：`ServiceRelationListResource` → `log_relation_list` → `process_service_relation` → `ServiceLogHandler.get_log_relations`。`get_log_relations` 正常返回完整 `value_list`，问题出在下一步：

```python
# apm_web.log.resources.process_service_relation
index_info = next(
    (i for i in indexes_mapping.get(bk_biz_id, []) if i["index_set_id"] in relation.value_list),
    None,
)
```

`next()` 只返回生成器的第一个元素。`value_list=[101, 102]` 时只有排在前面的那个被返回。

## 0x03 解决方案

将 `next()` 改为列表推导，遍历所有匹配项：

```python
matched = [i for i in indexes_mapping.get(bk_biz_id, []) if i["index_set_id"] in relation.value_list]
for index_info in matched:
    index_info = {**index_info}
    ...
    result.append(index_info)
```

注意事项：
- 需对 `index_info` 做浅拷贝后再修改 `addition`，避免共享引用导致多条结果互相覆盖。
- 外层 `log_relation_list` 已有按 `index_set_id` 去重，无需额外处理。
- 同文件 `process_span_host` / `process_datasource` / `process_metric_relations` 的 `next()` 均为单值匹配，不受影响。
