---
title: 优化首页 TraceID 全局搜索的预计算延迟
tags: [overview, search, apm, trace, pre-calculate, low-latency]
description: 在预计算路径之外补一条直查 APM 应用原始 Trace 的快速通道，解决新 Trace 在预计算未落盘时搜不到的问题
created: 2026-05-02
updated: 2026-05-02
---

# 优化首页 TraceID 全局搜索的预计算延迟

## 0x01 背景

### a. 现状

- 首页全局搜索 TraceID 走 `monitor_web.overview.search.TraceSearchItem`。
- 数据源仅为租户级共享的预计算结果表（`DataLink.pre_calculate_config.cluster[*].table_name`）。
- 预计算由实时聚合任务异步写入，从 Span 落原始库到落预计算库存在分钟级延迟。

### b. 痛点

- 用户复制刚产生的 TraceID 到首页搜索，分钟级窗口内持续返回空结果。
- 命中失败的现象与"无此 Trace"无法区分，用户无从判断是延迟还是真无数据。
- 现有路径无法绕过：预计算是唯一数据源。

### c. 目标

- 让用户在 Span 写入原始库后即可在首页搜到对应 Trace。
- 不削弱预计算路径对老数据的广度覆盖。
- 单次首页搜索的资源开销与响应时延控制在可接受范围。

## 0x02 需求范围

- `SearchSerializer` 增加非必填 `bk_biz_id`（用户当前所在业务），仅作候选输入，不强制语义。
- 在预计算路径之外新增一条"应用原始 Trace 直查"快速通道。
- 候选业务来源固定为：`bk_biz_id` 入参、`UserConfig.DEFAULT_BIZ_ID`、`UserConfig.FUNCTION_ACCESS_RECORD` 中 `apm_service` 的最近访问业务。
- 候选应用按"业务来源 + 服务数 + 最近访问次数"加权，取 TopN（默认 `15`）。
- 预计算路径与直查路径并行竞速，先返回非空者赢，另一路立即终止。
- 命中后装配的 item 字段与现有 `TraceSearchItem` 输出保持一致。

## 0x03 非目标

- 不替换、不重写预计算路径，老数据仍由预计算覆盖。
- 不引入应用级权限前置过滤（保留现状，由前端跳转时处理）。
- 不改动预计算任务本身的写入链路与频率。
- 不扩大候选业务为"用户全部有权限业务"，避免雪崩式 ES 并发。
- 不触碰 `Searcher` 调度结构与其它 `SearchItem` 的实现。

## 0x04 方法论

- 直查路径复用 `apm_web.handlers.db_handler.DbQuery.get_q` 的 `BK_APM` 数据源构造，时间字段切到 `OtlpKey.END_TIME`。
- 候选应用通过 `Application` 模型直接查询，不走 API 层。
- 加权策略与 TopN、并发与超时参数集中在 `TraceSearchItem` 内部，便于后续调参。
- 设计、文件级落点、加权公式、并发控制与验收标准统一沉淀到 [PLAN.md](./PLAN.md)。

## 0x05 验收标准

- 用户对一条新写入原始库、尚未进入预计算的 Trace，在首页搜索能在 `5s` 内命中。
- 老 Trace（已落预计算）的命中率与时延不退化。
- 直查路径 miss 时不抛错、不阻塞预计算路径返回。
- 直查并发数严格不超过 TopN 上限。
- 首个非空结果返回后其余查询立即终止。
- 候选业务/应用的去重、加权与业务来源覆盖在测试用例中可逐项追溯。

## 0x06 参考

- `monitor_web/overview/search.py`：`TraceSearchItem`、`Searcher`
- `monitor_web/overview/views.py`：`SearchSerializer`、`SearchViewSet`
- `monitor_web/overview/resources.py`：`GetFunctionShortcutResource.get_recent_shortcuts`
- `monitor/models/models.py`：`UserConfig.Keys.DEFAULT_BIZ_ID` / `FUNCTION_ACCESS_RECORD`
- `apm_web/models/application.py`：`Application.service_count`、`trace_result_table_id`
- `apm_web/handlers/db_handler.py`：`DbQuery.get_q`
