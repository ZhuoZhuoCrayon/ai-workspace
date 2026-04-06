---
title: mypy strict 模式合规改造
tags: [throttled-py, typing, mypy, strict]
description: 消除 mypy --strict 下全部 248 个类型错误，禁止 type: ignore，不改变运行时行为
created: 2026-04-06
updated: 2026-04-06
---

# mypy strict 模式合规改造

## 0x01 背景

### a. Why

`uv run mypy --strict throttled/` 报 **248 errors / 22 files**。项目已启用 `ruff ANN` 规则和 pre-commit `mypy-strict` 钩子，但历史代码未全量对齐。上一轮修复了 `BaseThrottledMixin` 的泛型参数化（[排障记录](../../troubleshooting/generic-mixin-type-narrowing.md)），现需扩展至全项目。

### b. 目标

- `mypy --strict` 0 errors
- 禁止 `# type: ignore`
- 不改变运行时行为
- `ruff check` + `pytest` 通过

## 0x02 实现路线

### a. 错误分类

- **缺失注解**（~70）：`utils.py`、`store/redis.py`、`store/redis_pool.py`、`rate_limiter/base.py`
- **联合类型泄漏**（~100）：async 侧 `_store`、`_atomic_actions`、`lock` 保留 sync|async 联合类型
- **Protocol 兼容性**（~30）：`do()` 返回类型不匹配、`__init__` 阻断 `type[Protocol]` 赋值
- **list 不变性**（~10）：`_DEFAULT_ATOMIC_ACTION_CLASSES` 使用 invariant 的 `list`
- **变量重定义**（~15）：`Quota` 字段、`_parse` 中 `options`/`parsed` 分支重定义
- **其他**（~23）：`no-any-return`、`valid-type`、`truthy-function`、`type-arg`

### b. 约束

- 不引入新的运行时依赖
- 不改变公共 API 签名（内部类型窄化可接受）
- 优先结构化修复，`cast` 仅用于泛型边界

## 0x03 参考

- [排障经验：同步异步共用 Mixin 的泛型类型窄化](../../troubleshooting/generic-mixin-type-narrowing.md)
- [mypy — Protocols and structural subtyping](https://mypy.readthedocs.io/en/stable/protocols.html)
