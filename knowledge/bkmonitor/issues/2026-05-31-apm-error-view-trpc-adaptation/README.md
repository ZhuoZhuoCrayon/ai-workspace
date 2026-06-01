---
title: 错误视图 tRPC 场景适配
tags: [apm, error-view, trpc, rpc, exception-type, scene-view]
description: 让 APM 错误视图在 tRPC/RPC 返回码错误中统一构造异常语义，并支持任务列表、趋势、详情和饼图联动
created: 2026-05-31
updated: 2026-06-01
---

# 错误视图 tRPC 场景适配

## 0x01 背景

### a. 痛点

APM 错误页面由任务列表、趋势、详情和饼图组成，页面通过 `exception_type` 完成联动过滤。

tRPC/RPC 返回码错误的 Span 满足 `status.code = 2`，但通常没有记录 `events.name = exception`。

当前页面依赖 `events.attributes.exception.type` 过滤异常，因此 tRPC/RPC 返回码错误无法在错误视图内形成完整联动。

### b. 当前进展

PR [#10784](https://github.com/TencentBlueKing/bk-monitor/pull/10784) 已在错误详情链路中构造特殊 Event，用于展示返回码标题与详情信息。

当前改动只覆盖错误详情。

任务列表、趋势和饼图仍沿用 `exception_type` 的默认事件过滤语义，无法按返回码来源字段完成联动。

## 0x02 目标

- 让 tRPC/RPC 返回码错误在错误视图中具备稳定的逻辑异常语义。
- 通过 `exception_refer` 表达 `exception_type` 的来源字段，支持前后端选择正确过滤条件。
- 让任务列表、趋势、详情和饼图在真实异常与返回码错误之间保持一致联动。
- 复用现有 `scene_view` 变量替换能力，不新增前端专项联动机制。

## 0x03 需求范围

- 后端返回错误分组时补充 `exception_refer`。
- 默认异常来源为 `events.attributes.exception.type`。
- tRPC/RPC 返回码来源为 `trpc.status_code` 或 `rpc.error_code`。
- `scene_view` 配置把 `exception_refer` 从任务列表行映射到下游 panel 请求。
- 趋势、详情和饼图根据 `exception_refer` 选择过滤条件。

## 0x04 非目标

- 本期不改变 Span 原始存储结构，不要求采集端补充真实异常事件。
- 本期不重构 APM 错误页面布局。
- 本期不扩展 tRPC/RPC 返回码备注、重定义和策略模板能力。
- 本期不引入新的前端状态管理机制。

## 0x05 方法论

- 先定义逻辑异常协议：`exception_type` 表示展示与分组值，`exception_refer` 表示过滤来源。
- 再把协议贯穿任务列表、趋势、详情和饼图，避免只在单个接口补 case-by-case 逻辑。
- 最后用 `scene_view` 配置验证 `$exception_refer` 能否随行选择进入下游 panel 请求。

## 0x06 验收标准

- 任务列表中真实异常行返回 `exception_refer = events.attributes.exception.type`。
- 任务列表中 tRPC/RPC 返回码错误行返回对应来源字段，例如 `trpc.status_code` 或 `rpc.error_code`。
- 选中真实异常行时，趋势、详情和饼图继续按 `events.name = exception` 与 `events.attributes.exception.type` 过滤。
- 选中 tRPC/RPC 返回码错误行时，趋势、详情和饼图按返回码字段过滤，且不混入同接口下其他异常类型。
- `apm_application-error.json` 与 `apm_service-service-default-error.json` 能通过 `$exception_refer` 传递联动上下文。
- 回归验证覆盖应用错误页与服务错误页的概览态、选中真实异常态和选中返回码错误态。

## 0x07 参考

- 实施方案：[PLAN.md](./PLAN.md)
- PR：[TencentBlueKing/bk-monitor #10784](https://github.com/TencentBlueKing/bk-monitor/pull/10784)
- `<源码>` view config 目录：`packages/monitor_web/scene_view/builtin/view_configs/`
- `<源码>` view config 文件：`apm_application-error.json`、`apm_service-service-default-error.json`
- `<源码>` bk-monitor/bkmonitor/packages/apm_web/handlers/span_handler.py
- `<源码>` bk-monitor/bkmonitor/packages/apm_web/meta/resources.py
- `<源码>` bk-monitor/bkmonitor/packages/apm_web/metric/resources.py
