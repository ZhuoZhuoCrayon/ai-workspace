---
title: Store 类型抽象边界优化
tags: [throttled-py, typing, store, abstraction, public-api, httpx]
description: 基于 HTTPX transport 设计调研，重新定义 BaseStore 的公共边界与内部 backend 配对边界
created: 2026-05-06
updated: 2026-05-06
---

# Store 类型抽象边界优化

## 0x01 背景

### a. Why

`mypy strict` 改造后，`BaseStore` 从直觉上的公共 store 边界变成了 `BaseStore[_BackendT]`。

这让用户代码里最自然的工厂签名无法通过类型检查：

```python
from throttled import BaseStore, store


def _get_store() -> BaseStore:
    return store.RedisStore(server="redis://127.0.0.1:6379/0")
```

当前可行写法是使用 `types.SyncStoreP`：

```python
from throttled import store, types


def _get_store(use_redis: bool) -> types.SyncStoreP:
    if use_redis:
        return store.RedisStore(server="redis://127.0.0.1:6379/0")
    return store.MemoryStore()
```

`SyncStoreP` 在类型上正确，但公共 API 手感绕。

问题不是用户误用：`BaseStore` 同时承担了公共能力边界、实现继承基类和 backend 配对载体。

### b. 目标

- 调研 HTTPX transport 抽象，明确主流库如何区分公共边界与底层实现细节。
- 梳理 throttled-py 当前 store、backend、atomic action、rate limiter 和 throttled 对象关系。
- 设计新的类型抽象边界，让 `BaseStore` 可以代表用户侧同步 store 能力。
- 保留 `mypy --strict` 的架构收益，不回退到 `Any`、裸 `cast` 或 `type: ignore`。
- 让文档、示例和测试不再需要用 `BaseStore[Any]` 或 `SyncStoreP` 解释普通同步 store 工厂。

## 0x02 需求范围

- 以 HTTPX 的 `BaseTransport`、`HTTPTransport`、`Client(transport=...)` 为对照样本。
- 重新定义 `throttled.store.BaseStore` 与 `throttled.asyncio.store.BaseStore` 的公共职责。
- 评估是否新增 backend-bound 实现辅助类，用于保留 store/backend/action 的精确配对。
- 同步审视 `BaseAtomicAction`、`BaseThrottledMixin` 与 `types.StoreP` 是否存在类似边界泄漏。
- 补齐类型验收用例，覆盖 `_get_store() -> BaseStore`、Redis / Memory 二选一和 `Throttled(store=...)`。
- 更新示例与文档中的推荐类型标注。

## 0x03 非目标

- 本期不改变限流算法语义。
- 本期不新增存储后端。
- 本期不替换 redis-py、fakeredis 或连接池实现。
- 本期不取消 `SyncStoreP` / `AsyncStoreP` 的结构化扩展能力。
- 本期不把所有内部泛型一刀切移除，只处理泄漏到公共边界的泛型。

## 0x04 方法论

- 先用源码证据确认 HTTPX 的对象分层，再抽象成可迁移原则。
- 再按 throttled-py 的运行时对象链路梳理职责边界。
- 方案只接受能够同时满足公共 API 顺滑和内部类型配对可检查的结构。
- 详细调研、对象图和开发方案统一沉淀到 [PLAN.md](./PLAN.md)。

## 0x05 验收标准

- `def _get_store() -> BaseStore` 可以返回 `MemoryStore` 或 `RedisStore`。
- `Throttled(store=_get_store())` 在 `mypy --strict` 下通过。
- async 侧存在对称方案，不通过同步 `BaseStore` 表达 async store。
- `BaseStore[Any]` 不再是测试 fixture、示例或文档中的常规推荐写法。
- `types.SyncStoreP` / `types.AsyncStoreP` 仅用于结构化第三方实现或内部泛型约束说明。
- `uv run --no-sync mypy throttled tests` 与项目既有测试入口通过。

## 0x06 参考

- [实施方案](./PLAN.md)
- [mypy strict 模式合规改造](../2026-04-06-mypy-strict-compliance/README.md)
- [排障经验：同步异步共用 Mixin 的泛型类型窄化](../../troubleshooting/generic-mixin-type-narrowing.md)
- [HTTPX Transports 文档](https://www.python-httpx.org/advanced/transports/)
