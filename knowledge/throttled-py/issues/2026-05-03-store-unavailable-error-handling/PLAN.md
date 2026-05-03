---
title: 优化存储不可用时的异常处理方案
tags: [throttled-py, store, redis, exception, reliability, planning]
issue: ./README.md
description: 基于 throttled-py 与外部仓库源码调研，定义 StoreUnavailableError 的统一包装方案与最小测试策略
created: 2026-05-03
updated: 2026-05-03
---

# 优化存储不可用时的异常处理 —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 调研与约束

### a. 当前异常泄漏路径

| 层次 | 代码入口 | 当前行为 | 影响 |
|------|----------|----------|------|
| Store | `throttled/store/redis.py`、`throttled/asyncio/store/redis.py` | `exists`、`ttl`、`expire`、`set`、`get`、`hset`、`hgetall` 直接调用 `get_client()` 与 Redis 命令 | 上层收到原始 Redis 异常 |
| AtomicAction 初始化 | `token_bucket`、`leaking_bucket`、`sliding_window`、`gcra` 的 Redis `*AtomicActionCoreMixin.__init__`（sync / async） | `register_script()` 无包装 | limiter 构造阶段异常类型不稳定 |
| AtomicAction 执行 | `fixed_window` 的 `incrby` / `expire` 与其他算法的 `_script(...)` | `do()` 无包装 | `limit()` / `peek()` 泄漏底层异常 |
| RateLimiter / Throttled | `BaseRateLimiterMixin._register_atomic_actions()`、`BaseThrottledMixin.limiter` | 懒初始化会放大前述差异 | 同一存储故障在不同算法上的抛错时机不一致 |

补充判断：

- `FixedWindow` 不走 `register_script()`，主要风险点在 `do()`。
- `TokenBucket`、`LeakingBucket`、`SlidingWindow`、`GCRA` 都会在 Redis AtomicAction 构造阶段注册脚本。
- `GCRA` 额外有 `peek` AtomicAction，不能只覆盖 `limit` 路径。

### b. 外部仓库对照

| 仓库 | 入口 | 机制 | 对本需求的启发 |
|------|------|------|----------------|
| `limits` | `limits/storage/base.py`、`limits/aio/storage/base.py` | 用 `_wrap_errors` + `__init_subclass__` 在基类统一织入 wrapper，按 `instance.base_exceptions` 捕获并包装成 `StorageError` | 统一包装应挂在基类，而不是分散到各个 store 方法 |
| `limits` | `limits/storage/redis.py`、`limits/aio/storage/redis/__init__.py` | Redis storage 自身声明 `base_exceptions`，脚本注册与命令执行共享同一异常族 | `base_exceptions` 应由 backend / storage 抽象层声明 |
| `redis_rate` | `redis_rate/rate.go` | `AllowN` / `AllowAtMost` 直接把 Redis 执行错误原样返回给调用方 | Go 风格偏向直接返回原始错误，不适合 `throttled-py` 当前“统一 catch 点”诉求 |
| `redis-py` | `redis/exceptions.py` | `RedisError` 覆盖连接、超时、服务端错误<br />`RedisClusterException` 独立成族 | Redis backend 不能只盯 `ConnectionError`，cluster 异常也要纳入 |

### c. 本期约束

- sync / async 行为必须对称。
- 统一异常类型使用现有的 `StoreUnavailableError`，不新增第二套公开异常。
- 通过 `raise ... from exc` 保留原始异常链，不要求额外扩展公开字段。
- 不包装 `throttled` 自身的 `DataError`、`SetUpError`。
- 测试按“每个目标文件只新增一个测试函数”的约束收敛。

## 0x02 方案主干

### a. 统一异常拓扑

```text
Redis / cluster client exception
-> Store 或 AtomicAction wrapper
-> StoreUnavailableError（raise ... from exc）
-> RateLimiter / Throttled 透明上抛
```

关键结论：

- `StoreUnavailableError` 是上层唯一稳定 catch 点。
- 原始 Redis 异常通过 `__cause__` 保留。
- `RateLimiter` 与 `Throttled` 不再各自补一层包装，避免重复转换。

### b. 结构分层

```text
BaseStoreBackend.base_exceptions
        ↓
BaseStore wrapper / BaseAtomicAction wrapper
        ↓
StoreUnavailableError
        ↓
RateLimiter / Throttled 透明上抛
```

本期只在 Store / AtomicAction 层做异常转换。

`RateLimiter` 与 `Throttled` 继续负责流程编排，不承担异常语义归一化。

### c. backend 异常声明

| 对象 | 设计 |
|------|------|
| `BaseStoreBackend` | 新增统一的 backend 基础异常声明能力，默认空集合 |
| `BaseRedisStoreBackend` | 懒解析 Redis 基础异常，至少覆盖 `redis.exceptions.RedisError` 与 `redis.exceptions.RedisClusterException` |
| `BaseMemoryStoreBackend` | 保持空集合，继续直接抛 `DataError` / `SetUpError` |

边界说明：

- Redis 依赖缺失时，当前构造路径仍会先走 `ImportError` / `SetUpError`。
- 这不属于“存储运行期不可用”包装范围。
- 自定义第三方 store 后端只要声明自己的 `base_exceptions`，即可自动接入同一套包装逻辑。

### d. wrapper 挂载点

| 层次 | 入口 | 处理方式 |
|------|------|----------|
| Store | sync / async `BaseStore` | 统一包住 `exists`、`ttl`、`expire`、`set`、`get`、`hset`、`hgetall` |
| AtomicAction 构造 | `BaseAtomicActionMixin` | 统一包住子类 `__init__`，覆盖 `get_client()` 与 `register_script()` |
| AtomicAction 执行 | sync / async `BaseAtomicAction` | 统一包住 `do()`，覆盖 `_script(...)` 与 `incrby` / `expire` |
| 上层 | `RateLimiter`、`Throttled` | 不额外 catch，直接透传统一异常 |

实现建议：

- 推荐参考 `limits`，用基类级别的统一 wrapper 织入，而不是在每个具体 store / action 方法内手写 `try/except`。
- 若采用 `__init_subclass__` 方案，需要加“已包装”标记，避免多继承链上的重复包装。
- `make_atomic()` 不需要单独包装。
- 只要 AtomicAction `__init__` 已统一处理，构造阶段异常就会自然收口。

### e. 对外行为语义

- `Throttled(...)` 保持现有懒初始化语义。
- 当调用 `limit()`、`peek()`、`__enter__()`、`__aenter__()`，
  或显式访问 `.limiter` 触发 limiter 构造时，
  若存储后端异常，统一抛出 `StoreUnavailableError`。
- hooks 不负责转换存储异常。
- 它们看到的仍然是统一后的异常。

### f. 为什么不完全照搬 `limits`

- `limits` 提供 `wrap_exceptions` 开关，允许调用方选择是否包装。
- `throttled-py` 已经存在公开异常 `StoreUnavailableError`，本需求的目标就是给上层一个稳定 catch 点。
- 本期更适合默认统一包装，不再额外引入新的用户开关，避免行为矩阵扩大。

## 0x03 开发落点

### a. 文件级改造

| 文件 | 场景 | 主要改动 | 测试点 |
|------|------|----------|--------|
| `throttled/store/base.py` | sync Store / AtomicAction 基类 | 增加 sync wrapper helper，并织入 Store 方法与 AtomicAction 构造 / 执行路径 | 代表性 sync store 操作抛 `StoreUnavailableError` |
| `throttled/asyncio/store/base.py` | async Store / AtomicAction 基类 | 增加 async wrapper helper，并织入 async Store 方法与 AtomicAction 执行路径 | 代表性 async store 操作抛 `StoreUnavailableError` |
| `throttled/store/redis.py` | Redis backend | 声明 Redis 基础异常集合 | Redis 命令与连接异常都能被识别 |
| `throttled/asyncio/store/redis.py` | async Redis backend | 复用同一异常声明逻辑 | async Redis 行为与 sync 对称 |

### b. 非改造主干

- `RateLimiter` 与 `Throttled` 不新增一层 `try/except`。
- 相关文件只承担调用链透传与公开入口验证。

## 0x04 测试策略

### a. 文件级测试布局

| 范围 | 文件 | 方式 |
|------|------|------|
| Store | `tests/store/test_store.py` | [1] 只新增 `1` 个测试函数<br />[2] 构造一个会抛 Redis 基础异常的 store 或 client stub，验证代表性 store 操作被统一包装 |
| Store（async） | `tests/asyncio/store/test_store.py` | [1] 只新增 `1` 个 async 测试函数<br />[2] 验证 async store 镜像行为 |
| Throttled | `tests/test_throttled.py` | [1] 只新增 `1` 个测试函数<br />[2] 通过公开 `Throttled.limit()` 断言上层拿到 `StoreUnavailableError` |
| Throttled（async） | `tests/asyncio/test_throttled.py` | [1] 只新增 `1` 个 async 测试函数<br />[2] 验证 async 公开入口 |
| RateLimiter | `tests/rate_limiter/test_store_unavailable.py` | [1] 新增测试文件，但只新增 `1` 个测试函数<br />[2] 按算法参数化构造所有 sync rate limiter，覆盖构造期与执行期两类失败 |
| RateLimiter（async） | `tests/asyncio/rate_limiter/test_store_unavailable.py` | [1] 新增 async 测试文件，但只新增 `1` 个 async 测试函数<br />[2] 按算法参数化构造所有 async rate limiter |

### b. 测试实现方式

- 不依赖真实 Redis 宕机或网络抖动。
- 使用可控的 broken client / monkeypatch 让 `register_script()`、`incrby()`、
  `expire()` 或 script call 稳定抛出 `redis.exceptions.ConnectionError`。
- `rate_limiter` 文件内同一个测试函数按算法参数化即可，不再为每种算法拆独立测试函数。

## 0x05 验收与验证

- 代表性 sync store 操作抛 `StoreUnavailableError`。
- 代表性 async store 操作抛 `StoreUnavailableError`。
- 所有 sync / async rate limiter 在存储异常时，`limit()` / `peek()` 主路径不再泄漏原始 Redis 异常。
- `Throttled.limit()`、`async Throttled.limit()` 抛统一异常类型。
- `DataError`、`SetUpError` 等本地参数 / 配置异常类型保持不变。

建议验证命令：

sync：

```bash
uv run pytest -n auto \
  tests/store/test_store.py \
  tests/test_throttled.py \
  tests/rate_limiter/test_store_unavailable.py \
  -x
```

async：

```bash
uv run pytest -n auto \
  tests/asyncio/store/test_store.py \
  tests/asyncio/test_throttled.py \
  tests/asyncio/rate_limiter/test_store_unavailable.py \
  -x
```

lint：

```bash
uv run prek run --files \
  throttled/store/base.py \
  throttled/asyncio/store/base.py \
  throttled/store/redis.py \
  throttled/asyncio/store/redis.py \
  tests/store/test_store.py \
  tests/test_throttled.py \
  tests/rate_limiter/test_store_unavailable.py \
  tests/asyncio/store/test_store.py \
  tests/asyncio/test_throttled.py \
  tests/asyncio/rate_limiter/test_store_unavailable.py
```

## 0x06 风险与约束

| 风险 | 说明 | 处理建议 |
|------|------|----------|
| 多继承重复包装 | `AtomicAction` 体系里存在 CoreMixin + BaseClass 多继承 | wrapper 增加“已包装”标记，避免重复织入 |
| Cluster 异常漏网 | `redis-py` 的 `RedisClusterException` 不完全属于 `RedisError` | Redis backend 的基础异常集合同时纳入两类基异常 |
| fakeredis 不易稳定复现网络异常 | 现有 fixture 更适合功能测试，不适合错误注入 | 新测试直接使用 stub / monkeypatch，避免依赖真实网络故障 |
| 构造时机差异 | `FixedWindow` 不注册脚本，其他算法会在构造期注册脚本 | `rate_limiter` 测试文件必须同时覆盖构造期与执行期两类失败 |

## 0x07 实施进展

| 时间 | 对应设计片段 | 结论调整概要 | 改动 / 验证 |
|------|--------------|--------------|-------------|
| `2026-05-03 00:00` | `0x01.a`、`0x02.c`、`0x04.a` | [1] 确认异常泄漏点不只在 `BaseStore`，还包括 AtomicAction `__init__` 与 `do()`。<br />[2] 参考 `limits`，优先采用“基类统一 wrapper”而不是分散手写 `try/except`。<br />[3] `rate_limiter` 测试需要单独建文件，并按算法覆盖构造期与执行期。 | [1] 已完成 `throttled-py` sync / async store、rate limiter、throttled 源码阅读。<br />[2] 已完成 `limits`、`redis_rate`、`redis-py` 对照调研。 |

## 0x08 参考

- `throttled/store/base.py`
- `throttled/asyncio/store/base.py`
- `throttled/store/redis.py`
- `throttled/asyncio/store/redis.py`
- `throttled/rate_limiter/fixed_window.py`
- `throttled/rate_limiter/token_bucket.py`
- `throttled/rate_limiter/leaking_bucket.py`
- `throttled/rate_limiter/sliding_window.py`
- `throttled/rate_limiter/gcra.py`
- `throttled/throttled.py`
- `throttled/asyncio/throttled.py`
- [<源码> limits limits/storage/base.py](https://github.com/alisaifee/limits/blob/master/limits/storage/base.py)
- [<源码> limits limits/aio/storage/base.py](https://github.com/alisaifee/limits/blob/master/limits/aio/storage/base.py)
- [<源码> limits limits/storage/redis.py](https://github.com/alisaifee/limits/blob/master/limits/storage/redis.py)
- [<源码> redis_rate rate.go](https://github.com/go-redis/redis_rate/blob/master/rate.go)
- [<源码> redis redis/exceptions.py](https://github.com/redis/redis-py/blob/master/redis/exceptions.py)

## 0x09 版本锚点

- 分支：待创建
- PR：待创建
