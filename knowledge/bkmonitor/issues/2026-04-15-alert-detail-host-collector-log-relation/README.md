---
title: 优化告警详情主机日志关联准确性
tags: [alert, log, host-target, collector, log-relation, accuracy]
description: 先修复日志类 HOST 告警的原始日志关联优先级，再接入主机关联采集项日志索引
created: 2026-04-15
updated: 2026-06-30
---

# 优化告警详情主机日志关联准确性

## 0x01 背景

### a. Why

新版告警详情的主机日志关联需要同时解决准确性和完整性问题。

准确性问题来自日志类 HOST 告警：日志策略按 `ip` 聚合后，告警对象会被建模为主机，但关联日志入口仍应优先回到原始日志策略配置。

完整性问题来自新版详情的目标聚合层：旧版告警详情通过 `listIndexByHost` 动态查询主机关联采集项日志索引，
新版 `alert_v2` 还没有把这类日志纳入 `HostTarget` 和 `BaseK8STarget` 的关联日志结果。

### b. 目标

- 优化日志类 HOST 告警的关联日志准确性。
- 在新版告警详情中支持查看主机关联采集项日志。
- 复用旧版 `listIndexByHost` 查询能力，避免重复造轮子。
- 将主机关联采集项日志能力纳入 `alert_v2` 目标聚合体系。
- 对 `HostTarget` 与 `BaseK8STarget` 统一补齐该能力。
- 保持前端无改动，仅通过后端返回结构扩展完成接入。

## 0x02 实现路线

### a. 建议的方案

以 `fta_web.alert_v2.target` 为统一收口层，分两个里程碑落地。

里程碑 1：`HostTarget.list_related_log_targets()` 先复用 `DefaultTarget.list_related_log_targets()`。
日志类 HOST 告警命中原始日志策略时，直接返回策略内的索引集、查询语句和维度过滤条件。

里程碑 2：直接依赖 `monitor_web.scene_view.resources.log.HostIndexQueryMixin` 查询主机关联采集项索引，再通过 `get_biz_index_sets_with_cache` 补全索引集元信息，最终并入 `list_related_log_targets()` 返回结果。

`BaseK8STarget` 基于 `list_related_host_targets()` 反查关联主机，再并发查询主机关联采集项日志。

`HostTarget` 在现有“关系图反查日志”能力之外，再补一路“主机关联采集项日志”查询，并通过统一的去重合并策略输出。

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
