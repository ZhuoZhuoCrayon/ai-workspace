---
title: throttled-py 可读容量配置 DSL 需求定义
tags: [throttled-py, quota, dsl, requirement]
description: 定义 quota 字符串 DSL 的需求边界与调研方法论，调研结论沉淀在 PLAN
created: 2026-04-04
updated: 2026-04-04
---

# throttled-py 可读容量配置 DSL 需求定义

## 0x01 背景与目标

### a. 背景

- RoadMap 对齐：`throttled-py` 2026H1 M1 已明确可读容量配置 DSL 为主线需求之一。
- 体验对齐：字符串 DSL 能降低接入门槛，减少对对象式 API 细节的记忆负担。
- 生态对齐：主流 Python 限流库普遍具备“人类可读限流表达”能力。

### b. 目标

- 产品目标：提供统一、易读、可迁移的 quota 字符串配置入口。
- 工程目标：在不破坏现有 API 的前提下扩展 DSL 能力。
- 交付目标：形成可执行需求基线，并将调研结论沉淀在 `PLAN.md` 用于实现阶段采信。

## 0x02 需求范围（v1）

### a. 功能范围

- 新增解析入口：`quota.parse("100/s; burst=200")`。
- 新增构造入口：`Throttled(quota="100/s; burst=200")`。
- 语法覆盖：支持基础速率表达、可读单位表达、多规则串联与 `burst` 参数。
- 兼容要求：现有 `Quota`、`Rate`、`per_sec`、`per_min` 等 API 保持可用。

### b. 非目标

- 本阶段不扩展到 `throttled-rs`。
- 本阶段不承诺覆盖所有未来多规则策略变体，仅确保与 `ANY_LIMITED_DENY` 主路径一致。
- 本文不承载调研细节、不承载实现细节，仅承载需求与方法论。

## 0x03 调研方法论

### a. 主流库样本（2026-04-04 快照）

- 框架集成型：`slowapi`、`Flask-Limiter`、`django-ratelimit`、`fastapi-limiter`。
- 通用能力型：`limits`、`pyrate-limiter`、`aiolimiter`。

### b. 调研方法

- 入口一致：优先采集官方文档与官方 README 的“用户第一入口语法”。
- 维度一致：统一比较单规则表达、多规则表达、可读性、可迁移性。
- 结论分层：需求文件仅记录方法论，语法结论与样例统一记录在 `PLAN.md`。

## 0x04 验收标准（需求侧）

- 边界清晰：需求范围、非目标、兼容边界明确可执行。
- 可实现性：需求条目可直接映射到实现任务与测试项。
- 可追溯性：调研结论与实现方案可在 `PLAN.md` 中逐项追溯。
