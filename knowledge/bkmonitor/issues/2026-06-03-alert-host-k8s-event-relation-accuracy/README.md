---
title: 主机场景容器事件关联准确性提升
tags: [alert, k8s-event, host-target, k8s-node, scene-view, unify-query]
description: 让主机与 K8S-NODE 告警按节点维度关联容器事件，避免跨节点 workload 事件混入并降低关联查询成本
created: 2026-06-03
updated: 2026-06-04
---

# 主机场景容器事件关联准确性提升

## 0x01 背景

### a. Why

新版告警详情在主机场景关联 K8S 容器事件时，当前路径是「主机 → workload → 事件」。

当 workload 跨节点时，该路径会混入其他节点事件。

同时，主机场景需要先查 workload 关系，再拼多 workload 事件条件，查询成本偏高。

### b. 目标

- 主机目标按节点维度关联 K8S 容器事件。
- K8S-NODE 目标不再被 namespace 前置条件拦截。
- 主机场景减少 workload 关系获取和多 workload 事件检索开销。

## 0x02 实现路线

### a. 建议的方案

- 主机目标通过 IP 查询 K8S 节点，并用 `host = node_name` 过滤容器事件。
- 主机目标查不到 K8S 节点时，不构造 K8S 事件查询。
- K8S-NODE 目标不再要求 namespace，并用 `host = node` 过滤节点上的事件。

### b. 约束

- workload 目标仍要求 namespace，避免 workload 事件查询范围失控。
- 本期不改变 K8S 事件采集和存储协议。
- 本期不改造 UnifyQuery 关系查询协议。
- 本期不新增前端交互或展示入口。
- 本期不调整 pod、service、workload 等其他 K8S 目标规则。

## 0x03 参考

- 实施方案：[PLAN.md](./PLAN.md)
- `<源码>` bk-monitor/bkmonitor/packages/fta_web/alert_v2/resources.py
- 改动点：`fta_web.alert_v2.resources.AlertEventBaseResource.build_k8s_query`
- 节点查询：`resource.scene_view.get_kubernetes_node(bk_biz_id=<bk_biz_id>, node_ip=<ip>)`
