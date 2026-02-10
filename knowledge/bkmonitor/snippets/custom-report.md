---
title: 自定义上报
tags: [custom-report, metrics, datasource]
description: 自定义指标上报相关的数据模型和流程
language: python
created: 2026-02-09
updated: 2026-02-09
---

# 自定义上报

## 0x01 关键信息

### a. 适用场景

自定义指标上报的创建流程、数据模型查询和调试。

### b. 创建流程

1. 创建自定义上报：`monitor_web.custom_report.resources.CreateCustomTimeSeries`
2. 创建 DataID：`metadata.resources.resources.CreateDataIDResource`
3. 创建 TimeSeriesGroup：`metadata.resources.resources.CreateTimeSeriesGroupResource`
4. 创建结果表：`metadata.models.result_table.ResultTable.create_result_table`

## 0x02 代码片段

### a. DataSource 数据结构

```json
{
  "bk_data_id": 564001,
  "token": "b68743f4af7746a387ad7f726d7ba79f",
  "data_name": "100729_custom_time_series_正式环境pod数据",
  "data_description": "100729_custom_time_series_正式环境pod数据",
  "mq_cluster_id": 129,
  "mq_config_id": 16826,
  "etl_config": "bk_standard_v2_time_series",
  "is_custom_source": true,
  "creator": "dathpan",
  "create_time": 1708594288,
  "last_modify_user": "dathpan",
  "last_modify_time": 1708594288,
  "type_label": "time_series",
  "source_label": "custom",
  "custom_label": null,
  "source_system": "bkmonitorv3",
  "is_enable": true,
  "transfer_cluster_id": "default",
  "is_platform_data_id": false,
  "space_type_id": "bkcc",
  "space_uid": "bkcc__100729"
}
```

### b. TimeSeriesGroup 数据结构

```json
{
  "bk_data_id": 564001,
  "bk_biz_id": 100729,
  "table_id": "100729_bkmonitor_time_series_564001.__default__",
  "max_rate": -1,
  "label": "application_check",
  "is_enable": true,
  "is_delete": false,
  "creator": "dathpan",
  "create_time": 1708594288,
  "last_modify_user": "dathpan",
  "last_modify_time": 1708594288,
  "is_split_measurement": true,
  "time_series_group_id": 7501,
  "time_series_group_name": "正式环境pod数据"
}
```

### c. ResultTable 数据结构

```json
{
  "table_id": "100729_bkmonitor_time_series_564001.__default__",
  "table_name_zh": "正式环境pod数据",
  "is_custom_table": true,
  "schema_type": "free",
  "default_storage": "influxdb",
  "creator": "dathpan",
  "create_time": 1708594288,
  "last_modify_user": "dathpan",
  "last_modify_time": 1708594288,
  "bk_biz_id": 100729,
  "is_deleted": false,
  "is_enable": true,
  "label": "application_check",
  "data_label": "prod_pod_data"
}
```

### d. 指标上报示例（Shell）

```shell
current_timestamp=$(date +%s%3N)
printf -v metric_data '{
  "data_id": 525129,
  "access_token": "fixme:自定义上报 Token",
  "data": [{
    "metrics": {
      "sand_cpu_load": 10,
      "sand_mem_usage": 30
    },
    "target": "127.0.0.1",
    "dimension": {
      "module": "db",
      "location": "guangdong"
    },
    "timestamp": %s
  }]
}' "${current_timestamp}"

curl -g -X POST "http://<bkop 中心化集群域名>:10205/v2/push/" \
  -H "Content-Type: application/json" \
  -d "$metric_data"
```

> 自定义上报周期调用节点管理轮训订阅：`metadata.task.custom_report.refresh_custom_report_2_node_man`
