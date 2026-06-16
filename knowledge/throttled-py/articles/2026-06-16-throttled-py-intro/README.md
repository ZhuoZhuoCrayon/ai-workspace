---
title: 为什么我又写了一个 Python 限流库：throttled-py
tags: [throttled-py, rate-limiting, python, redis, async]
description: 介绍开源 Python 限流库 throttled-py 的设计动机、核心功能与快速上手。
created: 2026-06-16
updated: 2026-06-16
---

# 为什么我又写了一个 Python 限流库：throttled-py

## 0x01 为什么做 throttled-py

限流不是拒绝服务，而是保护服务。

说白了，就是限制系统在单位时间内处理的请求数，挡住超出承载能力的流量。

CPU、内存、网络都是有限资源，突发流量一旦涌进来，资源很快被耗尽，服务跟着一起不可用。

举个常见的场景：某个客户端写了带重试的死循环，几秒内打来上万次请求。

没有限流，整台机器被它一个人拖垮，其他用户跟着遭殃。

有了限流，我还能按用户、调用方、优先级等维度分别设策略，把有限的资源留给更要紧的请求。

真正促使我动手的，是现有 Python 限流库的几处不足：

- 有的只支持同步、有的只支持异步，两套代码很难统一。
- 算法覆盖不全，个别实现还藏着性能问题。
- 存储后端常被锁死成一种，想换或想扩展都很费劲。

这三点凑在一起，就是 throttled-py 的起点。

## 0x02 核心功能

核心的限流能力如下：

- **同步异步同源**：一套 API 通吃，切到异步只需把 `import` 从 `throttled` 换成 `throttled.asyncio`。
- **算法齐全**：内置固定窗口、滑动窗口、令牌桶、漏桶和 GCRA（通用信元速率算法）`5` 种，覆盖常见限流形态。
- **选型有据**：令牌桶和 GCRA 允许突发，滑动窗口更平滑，漏桶恒定整流，固定窗口最简单但有临界突刺。
- **后端可插拔**：内置线程安全的内存（带过期淘汰的 LRU）和 Redis（单例、哨兵和集群），也支持自行扩展。

工程易用性方面：

- **配额即文档**：用字符串 DSL 描述，像 `1000/s burst 1000`、`1/m` 一样直白。
- **用法灵活**：提供函数调用、装饰器和上下文管理器三种形态，支持即刻返回或设 `timeout` 等待重试。
- **结果可判定**：`limit` 返回 `RateLimitResult`，`limited` 标记是否被限流，`state` 还带 `remaining`、`retry_after` 等明细。
- **接入 MCP**：可为 MCP Python SDK 的模型对话流程提供限流。
- **性能接近裸操作**：内存约为 `dict[key] += 1` 的 `2.5`～`4.5` 倍，Redis 约为 `INCRBY` 的 `1.06`～`1.37` 倍。

## 0x03 快速上手

### a. 安装

基础安装一条命令搞定，需要 Redis 后端再加装可选依赖。

```shell
pip install throttled-py

# 需要 Redis 后端
pip install "throttled-py[redis]"
```

### b. 基础用法

```python
from throttled import RateLimiterType, Throttled

throttle = Throttled(
    using=RateLimiterType.TOKEN_BUCKET.value,
    quota="1000/s burst 1000",
)

result = throttle.limit("/ping", cost=1)  # cost 是本次消耗的配额数
print(result.limited)  # True 表示这次请求被限流
```

不传参的 `Throttled()` 默认就是「内存 + 令牌桶 + 每分钟 `60` 次」，拿来就能用。

### c. 装饰器与 Redis

装饰器适合直接给某个函数套限流，超额时抛出 `LimitedError`，捕获它做降级或提示。

```python
from throttled import Throttled, exceptions

@Throttled(key="/ping", quota="1/m")
def ping() -> str:
    return "ping"

ping()
try:
    ping()  # 第二次调用超额，抛出 LimitedError
except exceptions.LimitedError as exc:
    print(exc)
```

想换成 Redis，把 `store` 换掉即可，算法和配额配置都不动。

```python
from throttled import RateLimiterType, Throttled, store

throttle = Throttled(
    using=RateLimiterType.TOKEN_BUCKET.value,
    quota="1000/s burst 1000",
    store=store.RedisStore(server="redis://127.0.0.1:6379/0", options={}),
)
```

### d. 接入 FastAPI

throttled-py 自带官方 FastAPI 集成，先装上对应的可选依赖。

```shell
pip install "throttled-py[fastapi]"
```

集成由三块拼起来：

- **`Limiter`**：给路由套限流，用 `@limiter.limit()` 装饰。
- **`RateLimitMiddleware`**：给放行的响应补上 `RateLimit-*` 头。
- **`rate_limit_exceeded_handler`**：超额时渲染成带 `Retry-After` 的 `429` 响应。

最小可用的例子如下：

```python
from fastapi import FastAPI, Request
from throttled.asyncio.contrib.fastapi import (
    Limiter,
    RateLimitExceededError,
    RateLimitMiddleware,
    rate_limit_exceeded_handler,
)

# 默认配额：同一方法 + 路由共享一个桶，这里是每分钟 2 次
limiter = Limiter("2/m")

app = FastAPI()
app.add_middleware(RateLimitMiddleware)
app.add_exception_handler(RateLimitExceededError, rate_limit_exceeded_handler)


# 路由装饰器要放在 @limiter.limit() 上面，顺序反了会静默失效
@app.get("/items")
@limiter.limit()
async def list_items(request: Request) -> dict[str, list[str]]:
    return {"items": ["apple", "banana"]}
```

被装饰的路由必须是 `async def`，并且参数里要有 `Request`。

想按调用方限流，就给 `Limiter` 传 `key_func`，比如用内置的 `get_remote_address` 按客户端 IP，或自定义函数按 API Key、用户 ID 区分。

## 0x04 参考

- 项目地址：[github.com/ZhuoZhuoCrayon/throttled-py](https://github.com/ZhuoZhuoCrayon/throttled-py)
