---
title: RUM 分层统一查询
tags: [rum, apm, query, span, view, session, factory, unify-query, semconv]
description: 用统一 Target、查询基类和语义字段目录承接 RUM 分层检索与 APM Trace 查询
created: 2026-08-07
updated: 2026-09-06
---

# RUM 分层统一查询

## 0x01 背景

### a. Why

RUM 已有通用原子查询 `BaseQuery` 和 Span 查询 `SpanQuery`，但还没有承接页面接口的统一业务层。若 Resource 直接依赖查询类，View、Session 接入时会复制一套接口和分派逻辑。

APM 后台仍通过独立查询基类和数据源配置字典选择原始表、预计算表与指标表，无法复用同一套查询原语和 `TraceDatasourceTarget` 协议。

### b. 目标

- Resource 注册一组 RUM 检索接口，通过 `mode` 选择查询层级。
- `RumLevelHandlerFactory` 通过统一映射入口分派 `span`，`view` 和 `session` 复用相同扩展结构。
- RUM Level 与 APM 的 3 类 Query 共用 `list[TraceDatasourceTarget]` 和通用查询原语。

## 0x02 实现路线

### a. 建议的方案

调用链固定为：`Resource → RumLevelHandlerFactory → LevelHandler → 一个或多个 Query → BaseQuery`。

APM 调用链固定为：`QueryProxy → list[TraceDatasourceTarget] → APM BaseQuery → 通用 BaseQuery`。原始表由 `table_id` 承载，预计算表由 `levels[name="trace"]` 承载。

详细类关系、接口清单和代码落点见 [实施方案](./PLAN.md)。

Span 各类型基础详情、字段引用和异步分析接口见 [Span 详情接口协议草稿](./pre-plan.md)。

### b. 约束

- 本方案不设计 View、Session 的数据生产或预计算过程。
- View、Session 基础查询只确定类名和代码位置，不展开实现。
- `BaseRumLevelHandler` 只持有 `data_sources`，查询对象由具体 Level 组合。
- Level 公共方法使用显式参数，差异化配置统一放入 `extra_config`。
- `extra_config` 只在服务端构造，不作为接口参数。
- 具体 Level 校验 `extra_config`，并拒绝覆盖公共参数或数据源。
- 三类 Level 共用一组 `/rum/search/{API}/` URL，不为层级复制接口。

## 0x03 参考

- [实施方案](./PLAN.md)
- [Span 详情接口协议草稿](./pre-plan.md)
- [RUM 数据协议](../../articles/2026-07-12-rum-span-data-protocol/README.md)
- `packages/rum_web/handlers/query/span.py`
- `bkmonitor/data_source/utils/query.py`
