---
title: 指标元信息存储与 SaaS/APM 自定义指标改造
tags: [metadata, custom-metric, apm, histogram]
description: 按完整隔离身份保存指标元信息，让指标管理与自定义视图按原名收敛 Histogram 成员。
created: 2026-09-15
updated: 2026-09-15
---

# 指标元信息存储与 SaaS/APM 自定义指标改造

## 0x01 背景

### a. Why

Histogram（直方图）上报后拆成 sum、count、bucket 等真实指标，当前管理页和自定义指标树逐项展示。用户需要自行识别成员、判断单位并组合运算；同名指标来自不同服务或插件时，也缺少统一的元信息身份。

### b. 目标

- 单位、原名、实际名称、描述、时间性与采集周期按数据源和隔离范围独立保存。
- 管理页按「原名 → 实际成员」展示，详情树选择一个 Histogram 后提供复合计算视图。
- SaaS 与 APM 共用模型和接口能力，已有单指标配置、查询和链接继续可用。

## 0x02 实现路线

### a. 建议的方案

扩展 `TimeSeriesMetric` 承接元信息，区分上报事实与用户配置。读取侧按隔离范围和原名组装指标族，图表沿用现有 `targets / query_configs / expression` 表达真实成员的多指标运算。

### b. 约束

- 本需求从 Metadata 接收元信息开始，Collector 采集、上报与传输是独立改造点。
- 页面分组只负责整理指标，不参与采集身份；实际查询必须保持服务、埋点库或插件隔离。
- 本期复合模板覆盖经典 Histogram，缺少可靠元信息时保留实际成员视图。
- 本期交付开发方案，告警策略、人工类型修正与采集任务级管理另行规划。

## 0x03 参考

- [开发方案](../../../../knowledge/bkmonitor/issues/2026-09-15-custom-metric-metadata/PLAN.md)。
- [Collector 元信息方案](../../../../knowledge/bkmonitor-datalink/issues/2026-09-15-collector-metric-metadata/PLAN.md)。
- [<源码> bk-monitor/bkmonitor/metadata/models/custom_report/time_series.py](https://github.com/TencentBlueKing/bk-monitor/blob/798e996354/bkmonitor/metadata/models/custom_report/time_series.py#L1861)。
- [<源码> bk-monitor/bkmonitor/packages/apm_web/custom_metric/resources.py](https://github.com/TencentBlueKing/bk-monitor/blob/798e996354/bkmonitor/packages/apm_web/custom_metric/resources.py#L35)。
