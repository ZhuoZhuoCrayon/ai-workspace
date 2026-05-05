---
title: 优化存储不可用时的异常处理
tags: [throttled-py, store, redis, exception, reliability]
description: 为存储后端异常提供统一的 StoreUnavailableError 包装，并以最小测试覆盖 sync / async 主路径
created: 2026-05-03
updated: 2026-05-05
---

# 优化存储不可用时的异常处理

## 0x01 背景与问题

### a. 背景

`throttled-py` 同时提供 sync / async 两套限流入口，并支持通过存储后端保存计数状态。

当 Redis 等外部存储不可用时，调用方需要一个稳定的异常捕获入口，才能把“存储不可用”与参数错误、配额错误等本地异常区分开。

### b. 当前问题

- `Store` 命令、`AtomicAction` 脚本注册和 `AtomicAction` 执行阶段都可能直接触达存储后端。
- 这些路径目前可能泄漏底层 Redis 异常，导致同一类存储故障在 `Store`、`RateLimiter`、`Throttled` 入口上的异常类型不稳定。
- 存储不可用异常与 `DataError`、`SetUpError` 等本地参数 / 配置异常缺少清晰语义边界。

## 0x02 目标

### a. 产品目标

- 为存储后端异常提供统一的公开异常类型：`throttled.exceptions.StoreUnavailableError`。
- 让 sync / async 公开入口在存储不可用时具备一致异常语义。
- 保持上层异常捕获入口稳定，使调用方只需面向 `StoreUnavailableError` 处理存储故障。

### b. 工程目标

- 保留原始异常链，便于排障时追溯底层 Redis 或其他存储后端异常。
- 不改变限流算法、配额计算、等待重试和本地参数校验语义。
- 为后续新增存储后端保留统一挂载点。

## 0x03 需求范围

### a. 需求项

- 识别存储后端声明的基础异常族，并将命中的底层异常统一包装为 `StoreUnavailableError`。
- 覆盖 `Store` 命令、`AtomicAction` 构造入口和 `AtomicAction` 执行入口。
- 覆盖 `RateLimiter.limit()`、`RateLimiter.peek()`、`Throttled.limit()` 等上层主路径。
- sync / async 路径保持行为对称。
- 补充最小测试，验证异常类型、异常链和上层透传行为。

### b. 非目标

- 本期不改变限流算法、配额计算或等待重试语义。
- 本期不把 `throttled` 自身的 `DataError`、`SetUpError` 归并到 `StoreUnavailableError`。
- 本期不新增用户可配置的异常包装开关或公开字段。
- 本期不扩展新的存储后端类型。

## 0x04 调研方法

### a. 项目内源码

- `throttled/store/base.py` 与 `throttled/asyncio/store/base.py`
- `throttled/store/redis.py` 与 `throttled/asyncio/store/redis.py`
- `throttled/rate_limiter/*` 与 `throttled/asyncio/rate_limiter/*`
- `throttled/throttled.py` 与 `throttled/asyncio/throttled.py`

### b. 外部样本

- `limits` 的 `wrap_errors` 机制
- `go-redis/redis_rate` 的 Redis 错误上抛方式
- `redis-py` 的异常层级定义

### c. 调研输出

- 明确当前异常泄漏点和公开入口影响面。
- 对齐统一包装应挂载的抽象层。
- 收敛满足最小增量约束的测试策略。
- 输出可供后续方案设计采信的边界、抽象层判断和测试策略。

## 0x05 验收标准

### a. 异常语义

- 当存储后端在连接、脚本注册、命令执行阶段出错时，sync / async 公共入口统一抛出 `StoreUnavailableError`。
- `limit()`、`peek()`、`Throttled.limit()` 等上层主路径不再泄漏原始 Redis 异常类型。
- 通过 `raise ... from exc` 保留原始异常链。
- `DataError`、`SetUpError` 等本地参数 / 配置异常类型保持不变。

### b. 测试与兼容

- `Store`、`RateLimiter`、`Throttled` 的 sync / async 主路径都有最小测试覆盖。
- 测试不依赖真实 Redis 宕机或网络抖动。
- 现有公共 API 使用方式保持兼容。
- 项目既有测试与文件级检查通过。

## 0x06 参考样本

- [<源码> limits limits/storage/base.py](https://github.com/alisaifee/limits/blob/master/limits/storage/base.py)
- [<源码> redis redis/exceptions.py](https://github.com/redis/redis-py/blob/master/redis/exceptions.py)
