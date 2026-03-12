---
title: 告警日志查询支持 Doris 数据源 —— 实施方案
tags: [log, unify-query, doris, data-source]
issue: knowledge/bkmonitor/issues/2026-03-12-log-query-doris-support/README.md
description: LogSearchTimeSeriesDataSource 重写 to_unify_query_config 将 _index 替换为 time
created: 2026-03-12
updated: 2026-03-12
---

# 告警日志查询支持 Doris 数据源 —— 实施方案

> 基于 `knowledge/bkmonitor/issues/2026-03-12-log-query-doris-support/README.md` 制定。

## 0x01 调研

### a. _index 使用链路

`_index` 作为指标字段出现在以下位置：

1. `LogSearchTimeSeriesDataSource.init_by_query_config`：未指定 `metric_field` 时默认 `{"field": "_index", "method": "COUNT"}`
2. `LogSearchLogDataSource.__init__`：`self.metrics = self.metrics or [{"field": "_index", "method": "COUNT"}]`

### b. to_unify_query_config 流程

父类 `BaseBkMonitorLogDataSource.to_unify_query_config` 遍历 `self.metrics`，将 `metric["field"]` 赋值给 `query["field_name"]`。当 `metric["field"] == "_index"` 时，`field_name` 原样传 `"_index"` 给 UnifyQuery。

`LogSearchTimeSeriesDataSource` 当前未重写此方法。

### c. 继承关系

```
BaseBkMonitorLogDataSource          ← to_unify_query_config 定义处
  └── LogSearchTimeSeriesDataSource ← 需要重写
        └── LogSearchLogDataSource  ← 自动继承
```

## 0x02 方案设计

在 `LogSearchTimeSeriesDataSource` 上重写 `to_unify_query_config`，调用父类实现后对 `field_name` 做映射替换。

```python
class LogSearchTimeSeriesDataSource(BaseBkMonitorLogDataSource):
    DORIS_INCOMPATIBLE_FIELDS: dict[str, str] = {"_index": "time"}

    def to_unify_query_config(self) -> list[dict]:
        query_list = super().to_unify_query_config()
        for query in query_list:
            field_name = query.get("field_name", "")
            if field_name in self.DORIS_INCOMPATIBLE_FIELDS:
                query["field_name"] = self.DORIS_INCOMPATIBLE_FIELDS[field_name]
        return query_list
```

设计要点：

- 使用类变量 `DORIS_INCOMPATIBLE_FIELDS` 做映射，便于后续扩展其他不兼容字段
- 仅在 UnifyQuery 配置生成阶段做替换，不修改 `self.metrics`，ES 老链路不受影响
- UnifyQuery 原始日志查询会在执行前清空 `field_name`，该路径不受本次替换影响

## 0x03 实施步骤

1. 在 `LogSearchTimeSeriesDataSource` 新增 `DORIS_INCOMPATIBLE_FIELDS` 类变量和 `to_unify_query_config` 重写
2. 验证矩阵：
   - UnifyQuery + ES：确认 `field_name` 从 `_index` 替换为 `time`，查询结果可用
   - UnifyQuery + Doris：确认 `field_name=time` 查询通过且结果可用
   - 非 UnifyQuery（直连 ES）：确认原有 `_index` 行为不受影响
3. 验收标准：
   - 三组场景均无报错
   - 与基线场景相比，关键统计结果在可接受误差范围内（按告警对账口径）

## 0x04 参考

- 涉及文件：`bkmonitor/bkmonitor/data_source/data_source/__init__.py`
- 父类实现：`BaseBkMonitorLogDataSource.to_unify_query_config`
- `_index` 使用场景：`init_by_query_config`、`LogSearchLogDataSource.__init__`

---
*制定日期：2026-03-12*
