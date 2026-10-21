---
title: APM 服务数据状态下沉到后台服务发现
tags: [apm, data-status, discover, heartbeat, topo-node, log, profiling]
description: 由各 telemetry 发现器落盘服务级数据心跳，让应用详情读取心跳判定状态，SaaS 下线请求侧状态重算
created: 2026-09-16
updated: 2026-10-21
---

# APM 服务数据状态下沉到后台服务发现

## 0x01 背景

### a. Why

APM 应用详情的四类数据状态（指标、日志、调用链、性能分析）在请求线程内实时重算。服务全集与状态判定分属两条链路，筛选栏要等状态接口返回才能结束 Loading。

慢 Trace `aa9a057ba090042a43eeb6012be6e024` 记录了应用 `hpjy_microservices_activities`（业务 `-4228598`、`100` 个服务）的一次 `service_list_async(column=data_status)` 请求，耗时 `5.235 s`，下游调用全部串行：

| 阶段 | 下游调用 | 耗时 |
| --- | --- | ---: |
| 服务全集枚举 | `QueryTopoNodeResource` | `401 ms` |
| 服务全集枚举 | `QueryProfileServicesDetail` | `404 ms` |
| 指标状态 | `bk_apm_count` 四路 UnifyQuery | `1211 ms` |
| 应用详情 | `DetailApplicationResource` | `162 ms` |
| 日志状态 | `es_query_dsl` 两次 terms 聚合 | `1607 ms` |
| 调用链状态 | Flow 指标 UnifyQuery | `314 ms` |
| 性能分析状态 | `QueryProfileServicesDetail(last_check_time__gt)` | `962 ms` |

后台服务发现每 `10 min` 扫描同一批数据，但只把结果写成服务拓扑，丢掉了「哪些服务在窗口内有数据」这个事实。请求侧只能用另一套查询重新证明同一件事。

### b. 目标

- 四类数据状态的数据来源全部由后台发现器落盘，应用详情只读不算。
- 新增按日志发现服务的能力，日志与其余三类数据源统一记录最后有数据时间。
- SaaS 删除服务级状态的重算逻辑、状态缓存与请求侧探测查询。

## 0x02 实现路线

### a. 建议的方案

**模型与抽象**

- 核心抽象：在 `TopoNode` 上增加 `heartbeat` 列，按数据类型分子键记录「最后有数据时间」与「最近检查完成时间」。
- 生产路径：调用链、指标、日志、性能分析四个发现器各自只合并自己数据类型的子键，沿用现有的读改写加批量更新写法。
- 读取路径：服务拓扑查询接口一次返回服务全集与四类心跳，SaaS 做纯映射得到三态。

**新增能力**

- 日志服务发现：从 APM 自身管理的日志结果表按 `resource.service.name`、`resource.server` 聚合服务名与最后数据时间，写入服务拓扑与心跳。
- 性能分析心跳并入：复用已有的 `ProfileService.last_check_time`，同时把服务写入服务拓扑，让服务全集收敛到单一事实源。

### b. 约束

- 日志发现只覆盖 APM 管理的日志结果表。服务关联索引的可用状态仍由 SaaS 读日志平台的 `NO_DATA` 标签判定，来源包括服务级手动关联、应用级全局关联与 K8S 关联日志。
- 应用级状态沿用 `Application.set_data_status` 按数据量判定的现有链路，不由服务级心跳聚合，口径不变。
- 本期不改造指标列（调用次数、错误率、平均耗时）的四路串行查询，不改造前端逐行渲染。
- eBPF 应用被排除在调用链发现调度之外，本期不补齐其调用链心跳，该类应用的调用链状态显示为无数据。
- 一并修复三处阻碍心跳取数的缺陷：指标发现查询窗口指向未来、日志聚合缺少 `size` 上限、关联索引判据只取首个匹配项。

### c. 实施状态

- 后台心跳生产、服务全集与服务列表状态读取已合入，服务列表改造见 [PR #12830](https://github.com/TencentBlueKing/bk-monitor/pull/12830)。
- 应用信息、Apdex 与告警图移除 `have_data()` 探测已完成开发与 review，[PR #12851](https://github.com/TencentBlueKing/bk-monitor/pull/12851) 待合入。
- 剩余功能为服务详情的性能分析心跳读取、性能分析应用的数据状态分类及旧对象清理，具体范围见 [实施方案](./PLAN.md)。

## 0x03 参考

- 方案：[PLAN.md](./PLAN.md)
- 慢 Trace：`aa9a057ba090042a43eeb6012be6e024`，在业务 `7` 的 `bkmonitor_production` 应用下查询
- 关联 issue：[APM 关联容器日志采集项慢接口优化](../2026-07-10-apm-k8s-log-relation-cache/README.md)
- 关联 issue：[APM 支持应用级别配置](../2026-03-04-apm-app-level-config/README.md)
