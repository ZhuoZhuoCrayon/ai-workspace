---
title: 优化 APM 日志关联列表关系查询长耗时
tags: [apm, log-relation, relation-query, unify-query, latency]
description: 记录 APM 日志关联列表接口在关系查询阶段出现 35s 级长耗时的优化需求与调研边界
created: 2026-05-06
updated: 2026-05-06
---

# 优化 APM 日志关联列表关系查询长耗时

## 0x01 背景

### a. 现象

- bkop 环境 Trace 样本显示，`POST /apm/service_log/log/log_relation_list/` 单次请求耗时 `36.09s`。
- 请求状态为 HTTP `200`，但 `apdex_type=frustrated`，用户体感为日志关联列表加载过慢。
- 样本请求是 APM 服务日志关联列表查询，时间窗口为 `7d`。

### b. 初步判断

主耗时集中在日志关联列表的关系查询分支：`api.unify_query.default.QueryMultiResourceRange` 耗时 `35.536s`，占总耗时约 `98.5%`。

## 0x02 目标

- 建立一个可追踪的优化需求，先固化现网样本、瓶颈位置和源码调用链。
- 后续优化方案必须基于多样本复核、UnifyQuery 服务端证据和请求规模分析再展开。
- 先避免在证据不足时直接改代码或写具体优化方案。

## 0x03 需求范围

- 记录当前 Trace 样本中的关键 span、耗时占比和接口参数特征。
- 定位 `LogRelationListResource` 到 `query_multi_resource_range` 的源码链路。
- 标记非主瓶颈：log-search 索引集查询、应用详情查询、IAM、MySQL 和 Redis 在当前样本中不是主耗时。
- 列出下一阶段必须补齐的观测证据。

## 0x04 非目标

- 本阶段不编写优化方案。
- 本阶段不修改 `log_relation_list`、`ServiceLogHandler` 或 `RelationQ` 代码。
- 本阶段不调整 UnifyQuery、日志平台或 APM 的缓存策略。
- 本阶段不基于单个样本直接推导全局结论。

## 0x05 验收标准

- [PLAN.md](./PLAN.md) 已记录样本 Trace、主瓶颈 span、耗时占比和源码链路。
- PLAN 明确当前只记录瓶颈，不包含具体优化方案。
- 后续排查所需证据清单可直接执行。

## 0x06 参考

- 样本 Trace：`bkmonitor_production / 9a9aaba7214aa92cd4edd6bfba7102b2`
- `<源码> bk-monitor/bkmonitor/packages/apm_web/log/resources.py`
- `<源码> bk-monitor/bkmonitor/packages/apm_web/handlers/log_handler.py`
- `<源码> bk-monitor/bkmonitor/packages/apm_web/topo/handle/relation/query.py`
