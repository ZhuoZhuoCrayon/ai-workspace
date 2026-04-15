---
title: 新版告警详情支持查看主机关联采集项日志
tags: [alert, log, host-target, collector, log-relation]
description: 在新版告警详情后端聚合主机关联采集项日志索引，复用旧版 listIndexByHost 逻辑并扩展 HostTarget 与 BaseK8STarget
created: 2026-04-15
updated: 2026-04-15
---

# 新版告警详情支持查看主机关联采集项日志

## 0x01 背景

### a. Why

旧版告警详情在前端通过 `listIndexByHost`
动态查询主机关联采集项日志索引，并据此展示日志入口。

新版告警详情已经切换为后端统一返回关联日志目标的模式。
但当前 `alert_v2`
的目标聚合逻辑尚未覆盖“主机关联采集项日志”这一能力。
这会导致主机类告警，以及具备 `bk_host_id + ip + bk_cloud_id`
维度的 K8S 告警，在新版详情中无法稳定看到对应采集项日志。

### b. 目标

- 在新版告警详情中支持查看主机关联采集项日志。
- 复用旧版 `listIndexByHost` 查询能力，避免重复造轮子。
- 将主机关联采集项日志能力纳入 `alert_v2` 目标聚合体系。
- 对 `HostTarget` 与 `BaseK8STarget` 统一补齐该能力。
- 保持前端无改动，仅通过后端返回结构扩展完成接入。

## 0x02 实现路线

### a. 建议的方案

以 `fta_web.alert_v2.target` 为统一收口层。
直接依赖 `monitor_web.scene_view.resources.log.HostIndexQueryMixin`
查询主机关联采集项索引，再通过 `get_biz_index_sets_with_cache`
补全索引集元信息，最终并入 `list_related_log_targets()`
返回结果。

`BaseK8STarget` 基于 `list_related_host_targets()`
反查关联主机，再并发查询主机关联采集项日志。

`HostTarget` 在现有“关系图反查日志”能力之外，
再补一路“主机关联采集项日志”查询，并通过统一的去重合并策略输出。

### b. 约束

- 不考虑前端改动。
- 旧版 `listIndexByHost` 行为不变。
- 主机采集项查询优先复用现有 mixin，不新增外部接口协议。
- 多路日志查询需要使用线程池并发加速。
- 出现重复索引集时仅保留一份结果，并记录日志。

## 0x03 参考

- `packages/monitor_web/scene_view/resources/log.py`
- `packages/monitor_web/alert_events/resources/frontend_resource.py`
- `packages/fta_web/alert_v2/target.py`
- `packages/fta_web/alert_v2/resources.py`
- `packages/apm_web/strategy/views.py`
