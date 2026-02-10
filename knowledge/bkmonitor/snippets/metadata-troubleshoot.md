---
title: Metadata 关联排查
tags: [metadata, datasource, result-table, kafka, troubleshoot]
description: 指标无数据时的 Metadata 关联排查流程
language: python
created: 2026-02-09
updated: 2026-02-09
---

# Metadata 关联排查

## 0x01 关键信息

### a. 适用场景

指标无数据时，排查数据源、结果表、Kafka Topic 等 Metadata 关联关系。

### b. 核心概念

- **数据源（DataSource）**：数据接收侧相关配置
- **结果表（ResultTable）**：数据落盘相关的配置

## 0x02 代码片段

### a. 指标无数据排查流程

```python
from metadata import models
from kafka import KafkaConsumer

# 1. 获取 DataID - ResultTable 关系
models.DataSourceResultTable.objects.filter(
    table_id__contains="489_bkapm_metric_test_syyxs_apm.__default__"
).first().__dict__
# 结果：bk_data_id: 1576294, table_id: '489_bkapm_metric_test_syyxs_apm.__default__'

# 2. 获取数据源信息
models.DataSource.objects.filter(bk_data_id=1576294).first().__dict__
# 关键字段：token, mq_cluster_id, mq_config_id, etl_config

# 3. 获取结果表信息
models.ResultTable.objects.filter(
    table_id="489_bkapm_metric_test_syyxs_apm.__default__"
).first().__dict__
# 关键字段：default_storage, bk_biz_id, label

# 4. 查询结果表所在存储集群（包括消费组）
models.KafkaStorage.objects.filter(
    table_id='489_bkapm_metric_test_syyxs_apm.__default__'
).first().__dict__
# 关键字段：topic, partition, storage_cluster_id

# 5. 根据 storage_cluster_id 查询存储集群信息
models.ClusterInfo.objects.get(cluster_id=158).__dict__
# 关键字段：domain_name, port

# 6. 获取已同步的指标和维度数量
models.ResultTableField.objects.filter(
    table_id='489_bkapm_metric_test_syyxs_apm.__default__'
).count()

# 7. 根据 DataID 找到 GSE 侧 Kafka Topic
models.KafkaTopicInfo.objects.filter(bk_data_id=1576294).first().__dict__
# 关键字段：topic, partition

# 8. 根据 mq_cluster_id 找到 GSE 侧 Kafka 集群信息
models.ClusterInfo.objects.get(cluster_id=99).__dict__
# 关键字段：domain_name, port

# 9. 接收 Kafka 消息验证数据
c = KafkaConsumer('0bkmonitor_15762940', bootstrap_servers='<domain_name>:<port>')
for m in c:
    print(m)
```

### b. ES 查询示例 DSL

```json
{
  "query": {
    "bool": {
      "filter": [
        {
          "range": {
            "end_time": {
              "gt": 1722169881000000,
              "lte": 1722342690000000
            }
          }
        }
      ]
    }
  },
  "sort": [{"end_time": {"order": "desc"}}],
  "aggs": {
    "__dist_05": {
      "aggs": {
        "func": {
          "aggs": {
            "service_name": {
              "terms": {
                "order": {"_count": "desc"},
                "field": "resource.service.name",
                "size": 10000
              }
            }
          },
          "terms": {
            "order": {"_count": "desc"},
            "field": "span_name",
            "size": 10000
          }
        }
      },
      "terms": {
        "order": {"_count": "desc"},
        "field": "kind",
        "size": 10000
      }
    }
  },
  "size": 0
}
```
