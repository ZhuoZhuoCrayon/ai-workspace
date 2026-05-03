---
title: 优化存储不可用时的异常处理
tags: [throttled-py, store, redis, exception, reliability]
description: 为存储后端异常提供统一的 StoreUnavailableError 包装，并以最小测试覆盖 sync / async 主路径
created: 2026-05-03
updated: 2026-05-03
---

# 优化存储不可用时的异常处理

## 0x01 背景与目标

### a. 当前问题

- 当前 Store 在连接或操作存储后端时，没有统一捕获底层异常。
- 当前 AtomicAction 在脚本注册和执行阶段，也会直接泄漏底层异常。
- 同一类存储故障在 `Store`、`RateLimiter`、`Throttled` 不同入口上的异常类型和抛错时机不稳定，不利于上层统一处理“存储不可用”场景。

详细源码调研见 [PLAN.md](./PLAN.md)。

### b. 本期目标

- 为存储后端异常提供统一的公开异常类型：`throttled.exceptions.StoreUnavailableError`。
- 覆盖 sync / async 两套主路径。
- 保持上层 catch 点稳定，不改变限流算法本身的语义。

## 0x02 需求范围

### a. 需求项

- 增加统一异常包装，识别特定存储的基础异常，异常时抛出 `StoreUnavailableError`。
- 覆盖 `BaseStore` 的存储操作方法。
- 覆盖 `BaseAtomicAction` 的构造与 `do()`，确保 `register_script()` 等初始化异常也被统一包装。
- 查漏补缺所有会直接触达存储后端的 sync / async 主路径。
- 补充最小测试，验证存储异常时抛出准确异常类型。

### b. 非目标

- 本期不改变限流算法、配额计算或等待重试语义。
- 本期不把 `throttled` 自身的 `DataError`、`SetUpError` 归并到 `StoreUnavailableError`。
- 本期不扩展新的存储后端类型，只要求当前实现为后续扩展保留统一挂载点。

## 0x03 调研方法

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

- 明确当前异常泄漏点。
- 对齐统一包装应挂载的抽象层。
- 收敛满足最小增量约束的测试策略。

## 0x04 验收标准

### a. 异常语义

- 当存储后端在连接、脚本注册、命令执行阶段出错时，sync / async 公共入口统一抛出 `StoreUnavailableError`。
- `limit()`、`peek()`、`Throttled.limit()` 等上层主路径不再泄漏原始 Redis 异常类型。
- 通过 `raise ... from exc` 保留原始异常链。

### b. 测试约束

- `tests/store/test_store.py` 只新增 `1` 个测试函数。
- `tests/test_throttled.py` 只新增 `1` 个测试函数。
- `rate_limiter` 单独新增测试文件，但每个文件只新增 `1` 个测试函数。
- async 镜像测试按同样约束处理。

### c. 兼容边界

- 本期只统一“存储不可用”异常语义。
- 现有限流算法、重试等待和参数校验语义保持不变。

## 0x05 参考

- [实施方案](./PLAN.md)
- [<源码> limits limits/storage/base.py](https://github.com/alisaifee/limits/blob/master/limits/storage/base.py)
- [<源码> redis redis/exceptions.py](https://github.com/redis/redis-py/blob/master/redis/exceptions.py)
