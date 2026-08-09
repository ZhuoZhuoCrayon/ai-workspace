---
title: RUM 分层统一查询
tags: [rum, query, span, view, session, factory, unify-query]
description: 用 mode 将同一组 RUM 检索接口分派到 Span、View 和 Session 查询层
created: 2026-08-07
updated: 2026-08-09
---

# RUM 分层统一查询

## 0x01 背景

### a. Why

RUM 已有通用原子查询 `BaseQuery` 和 Span 查询 `SpanQuery`，但还没有承接页面接口的统一业务层。若 Resource 直接依赖查询类，View、Session 接入时会复制一套接口和分派逻辑。

### b. 目标

- Resource 注册一组 RUM 检索接口，通过 `mode` 选择查询层级。
- `RumLevelHandlerFactory` 首期注册 `span`，并为后续 `view`、`session` 保留同一映射入口。
- Level 以 `list[TraceDatasourceTarget]` 初始化，可按需组合多个 `BaseQuery` 子类。

## 0x02 实现路线

### a. 建议的方案

调用链固定为：`Resource → RumLevelHandlerFactory → LevelHandler → 一个或多个 Query → BaseQuery`。

详细类关系、接口清单和代码落点见 [实施方案](./PLAN.md)。

### b. 约束

- 本方案不定义请求字段、响应字段和错误码。
- 本方案不设计 View、Session 的数据生产或预计算过程。
- View、Session 基础查询只确定类名和代码位置，不展开实现。
- `BaseRumLevelHandler` 只持有 `data_sources`，查询对象由具体 Level 组合。
- Level 公共方法使用显式参数，差异化配置统一放入 `extra_config`。
- 具体 Level 校验 `extra_config`，并拒绝覆盖公共参数或数据源。
- 三类 Level 共用一组 `/rum/search/{API}/` URL，不为层级复制接口。

## 0x03 参考

- [实施方案](./PLAN.md)
- [RUM 数据协议](../../articles/2026-07-12-rum-span-data-protocol/README.md)
- `packages/rum_web/handlers/query/span.py`
- `bkmonitor/data_source/utils/query.py`
