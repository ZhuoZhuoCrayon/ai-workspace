---
title: 指标元信息存储与 SaaS/APM 自定义指标改造
tags: [metadata, custom-metric, apm, histogram, bmw]
description: 采用取值去重方案，元信息按内容去重为取值，每个 scope 一行存取值 ID 列表，支持按服务过滤、编辑和分组，Histogram 按原名组族，指标项表零 DDL，页面分组表加两列。
created: 2026-09-15
updated: 2026-10-14
---

# 指标元信息存储与 SaaS/APM 自定义指标改造

## 0x01 背景

### a. Why

Histogram（直方图）上报后拆成 sum、count、bucket 等真实指标，当前管理页和自定义指标树逐项展示。用户需要自行识别成员、判断单位并组合运算。

元信息按来源上报：同一数据源下的同名指标可能来自上百个服务。按来源逐份保存会让存储随来源线性膨胀，而这些来源的元信息绝大多数相同。

APM 自定义指标 V2 用 BkBase（蓝鲸数据平台）的分组发现，把 OpenTelemetry instrumentation scope 名 `scope_name` 放进指标项身份。分组默认不含服务，服务归属只能靠 Redis 白名单补充。

### b. 目标

- 指标项唯一键不变，其中的范围段 `field_scope` 固定为 `default` 后每个指标名一行，服务与 scope 等上报来源不再进入指标项身份。
- 元信息按内容去重为取值，每个 scope 一行存取值 ID 列表；用户按服务修改时写入独立覆盖表。
- 策略、检索选择器与自定义指标页读取同一份有效配置，用户配置优先于上报值。
- 管理页按「原名 → 实际成员」展示，详情树选择一个 Histogram 后提供多 target 复合视图。
- SaaS 与 APM 共用模型和接口能力，保留项的单指标配置、查询、视图与链接继续可用。

## 0x02 实现路线

### a. 建议的方案

指标项（`TimeSeriesMetric`）继续由 BkBase 指标同步维护，`field_scope` 固定为 `default`。bmw（Go 后台任务服务 bk-monitor-worker）消费 Collector（采集组件 bk-collector）推送的元信息，按内容去重写入取值表（`TimeSeriesReportValue`）。上报范围表（`TimeSeriesReportScope`）用 `labels` 保存服务等标签，并用 `report_value_ids` 记录该 scope 上报的取值 ID。用户按服务修改时写入 `TimeSeriesMetricOverride`。

`TimeSeriesScope` 收窄为页面分组。存量 APM V2 数据源逐个用单事务收敛，即把同名的多行指标项合并为 `field_scope=default` 的一行，并关闭 BkBase 分组发现。读取侧按定义组装指标族，图表沿用现有 `targets / query_configs / expression` 表达多指标运算。

### b. 约束

- 本需求从 bmw 消费元信息开始，Collector 采集、上报与传输是独立改造点。
- 保留 BkBase 指标同步：指标名、维度与活跃状态仍由现有同步任务维护。
- 废弃 BkBase APM 指标分组发现（v2 `group_dimensions`）：该方式默认不含服务、无法按服务隔离，分组与服务归属改由 Collector 推送的元信息发现。
- 页面分组只负责整理指标，不参与元信息身份，可见指标项的 `field_id` 在迁移中保持有效。
- 平台需兼容 MySQL `5.7`，存储方案不依赖 JSON 多值索引。
- 线上链路持续运行：指标项表零 DDL，页面分组表增加选择器两列并换唯一键。任一组件先发布、迁移被吞（迁移失败而发布未中断）或新旧版本共存时，存量同步与查询不受影响。
- 本期复合面板覆盖经典 Histogram（拆成 `_sum`、`_count`、`_bucket` 的显式分桶直方图），缺少可靠元信息时保留实际成员视图，告警策略、人工类型修正与采集任务级管理另行规划。

## 0x03 参考

- [开发方案](./PLAN.md)。
- [存储选型与压测报告](./REPORT.md)，复现工程见 [validation](./validation/README.md)。
- [Collector 元信息方案](../../../../knowledge/bkmonitor-datalink/issues/2026-09-15-collector-metric-metadata/PLAN.md)。
- [<源码> bk-monitor/bkmonitor/metadata/models/custom_report/time_series.py](https://github.com/TencentBlueKing/bk-monitor/blob/master/bkmonitor/metadata/models/custom_report/time_series.py)。
- [<源码> bk-monitor/bkmonitor/packages/apm_web/custom_metric/resources.py](https://github.com/TencentBlueKing/bk-monitor/blob/master/bkmonitor/packages/apm_web/custom_metric/resources.py)。
- 调研文档《自定义指标开箱即用调研》保存在本地 `references/`，不入库。
