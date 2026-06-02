---
title: 主机场景容器事件关联准确性提升
tags: [alert, k8s-event, host-target, k8s-node, scene-view, unify-query]
description: 让主机与 K8S-NODE 告警按节点维度关联容器事件，避免跨节点 workload 事件混入并降低关联查询成本
created: 2026-06-03
updated: 2026-06-03
---

# 主机场景容器事件关联准确性提升

## 0x01 背景

### a. 痛点

新版告警详情在关联 K8S 容器事件时，主机场景当前先通过 UnifyQuery 获取 K8S workload，再查询对应 workload 事件。

该路径把 workload 当作主机与容器事件之间的中间层。

当 workload 跨节点时，查询结果会混入不属于当前节点的事件。

### b. 影响

- 主机告警的容器事件关联结果可能包含其他节点的事件。
- workload 关系查询耗时会直接影响告警详情关联事件加载。
- 关联 workload 数量较多时，下游事件检索条件会膨胀，检索性能和稳定性都会下降。

## 0x02 目标

- 主机目标按节点维度关联 K8S 容器事件。
- K8S-NODE 目标不再被 namespace 前置条件误拦截。
- workload 目标继续保留 namespace 约束。
- 主机场景减少 workload 关系获取与多 workload 事件检索开销。

## 0x03 需求范围

- 主机目标通过 IP 查询 K8S 节点信息，并使用 `host = node_name` 过滤容器事件。
- 主机目标查询到 `bcs_cluster_id` 时，事件查询应继续带上集群范围。
- K8S-NODE 目标允许在没有 namespace 的情况下构造节点事件查询。
- workload 目标仍要求 namespace，避免 workload 事件查询范围失控。
- 未查询到 K8S 节点时，不构造宽泛的 workload 兜底查询。

## 0x04 非目标

- 本期不改变 K8S 事件采集、存储和字段协议。
- 本期不改造 UnifyQuery workload 关系查询协议。
- 本期不新增前端交互或展示入口。
- 本期不扩展 pod、container 等其他目标类型的事件关联规则。

## 0x05 方法论

- 先拆分目标类型语义：主机和 K8S-NODE 属于节点维度，workload 属于命名空间维度。
- 再把主机路径从「主机 → workload → 事件」收敛为「主机 IP → 节点名称 → 事件」。
- 最后用跨节点 workload、无 namespace 的 K8S-NODE 和非 K8S 主机做回归验证。

## 0x06 验收标准

- 主机目标 IP 能查询到 K8S 节点时，`build_k8s_query` 构造的事件过滤条件包含 `host = node_name`。
- 主机目标的容器事件关联不再依赖 workload 关系列表。
- 同一个 workload 分布在多个节点时，主机目标只返回当前节点的 K8S 事件。
- K8S-NODE 目标即使没有 namespace，也能构造节点事件查询。
- workload 目标缺少 namespace 时，仍不会构造 workload 事件查询。
- 非 K8S 主机不会返回仅由 workload 关系推导出的跨节点容器事件。

## 0x07 参考

- 实施方案：[PLAN.md](./PLAN.md)
- `<源码>` bk-monitor/bkmonitor/packages/fta_web/alert_v2/resources.py
- 改动点：`fta_web.alert_v2.resources.AlertEventBaseResource.build_k8s_query`
- 节点查询：`resource.scene_view.get_kubernetes_node(bk_biz_id=<bk_biz_id>, node_ip=<ip>)`
