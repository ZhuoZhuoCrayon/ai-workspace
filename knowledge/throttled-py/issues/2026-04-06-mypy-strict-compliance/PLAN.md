---
title: mypy strict 模式合规改造方案
tags: [throttled-py, typing, mypy, strict]
issue: ./README.md
description: 四阶段修复 248 个 mypy --strict 错误的实施方案
created: 2026-04-06
updated: 2026-04-06
---

# mypy strict 模式合规改造 —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 调研

### a. 错误热点分析

按文件统计（截取 top 7）：

- `throttled/utils.py`：~35 errors — 缺失注解（Timer、Benchmark、import_string）
- `throttled/store/redis_pool.py`：~15 errors — redis 类型别名、参数 Optional、工厂方法注解
- `throttled/store/redis.py`：~15 errors — `_set_*` 返回注解、`_parse` 内变量重定义
- `throttled/asyncio/rate_limiter/*.py`：~80 errors — async 联合类型泄漏（lock、store、atomic action）
- `throttled/asyncio/store/memory.py`：~10 errors — `_get_lock` classmethod vs instancemethod、lock 联合类型
- `throttled/rate_limiter/base.py`：~6 errors — Quota dataclass、Registry/Meta 注解缺失
- `throttled/exceptions.py`：1 error — `message` 变量重定义

### b. 核心矛盾

async 侧错误占总量 ~60%，根因与 `BaseThrottledMixin` 相同——sync/async 共用基类导致属性类型为联合类型：

```text
BaseRateLimiterMixin
├── _store: StoreP (= _SyncStoreP | _AsyncStoreP)
├── _atomic_actions: dict[str, AtomicActionP (= Sync | Async)]
│
├── sync BaseRateLimiter ── .do() → tuple          ✓ 直接用
└── async BaseRateLimiter ── await .do() → ???      💥 union 不可 await
```

## 0x02 方案设计

### a. async 侧类型窄化（属性重注解）

上一轮 `BaseThrottledMixin` 采用 `Generic[_LimiterT, _HookT]`，但 `BaseRateLimiterMixin` 存在 CoreMixin 菱形继承 + `RateLimiterMeta` 元类，Generic 化成本高且引入 MRO 风险。

**方案**：在 async `BaseRateLimiter` 中直接声明更窄的属性类型（类型窄化，非 Generic）。

涉及文件：`throttled/asyncio/rate_limiter/base.py`

```python
class BaseRateLimiter(rate_limiter.BaseRateLimiterMixin, metaclass=RateLimiterMeta):
    _store: _AsyncStoreP                                        # 窄化
    _atomic_actions: dict[AtomicActionTypeT, _AsyncAtomicActionP]  # 窄化
```

同理，`throttled/asyncio/store/memory.py` 中窄化 lock 类型：

```python
class MemoryStoreBackend(store.MemoryStoreBackend):
    lock: _AsyncLockP

    @classmethod
    def _get_lock(cls) -> _AsyncLockP:
        return asyncio.Lock()
```

### b. AtomicAction Protocol 修复

两个问题：

1. `do()` 返回 `tuple[int, ...]`，但具体实现返回 `tuple[int, int, float, float]` 等含 float 元组
2. `__init__(backend: StoreBackendP)` 导致 `type[ConcreteClass]`（参数更窄）无法赋给 `type[Protocol]`

**修复**：

- `do()` 返回类型 → `tuple[int | float, ...]`（覆盖所有具体实现）
- 从 Protocol 移除 `__init__`（构造器不属于实例结构契约）
- 同步修改 `BaseAtomicAction`（ABC）的 `do()` 返回类型

涉及文件：`throttled/types.py`、`throttled/store/base.py`、`throttled/asyncio/store/base.py`

### c. list → Sequence（协变容器）

`_DEFAULT_ATOMIC_ACTION_CLASSES: list[type[AtomicActionP]]` 中 `list` 是 invariant，子类赋值报错。

**修复**：改用 `Sequence`（covariant）。涉及所有 CoreMixin 和 concrete rate limiter 类。

### d. Quota dataclass

`period_sec: int = None` 声明 `int` 但默认 `None`，`__post_init__` 中才赋值。

**修复**：使用 `field(init=False)` 声明计算字段，`__post_init__` 中赋值并加类型注解。

### e. 工具函数与连接池注解补全

纯注解补全工作，无架构变更。按 mypy 报错逐项修复。

## 0x03 实施步骤

### a. 基础注解补全

| 文件 | 改动 |
|------|------|
| `throttled/utils.py` | Timer、Benchmark 全部方法加注解；`_callback` 改 Optional；`_start` 消除 redef；`import_string` 加返回类型 |
| `throttled/exceptions.py` | `message` 变量消除 `no-redef` |
| `throttled/rate_limiter/base.py` | Quota 计算字段用 `field(init=False)`；`register`、`__new__` 加注解 |
| `throttled/store/redis.py` | `_set_*` → `-> None`；`_parse` 内 `options`/`parsed` 消除 redef |
| `throttled/store/redis_pool.py` | `DefaultParser` TypeAlias；`url` → Optional；工厂方法注解；redis union 处理 |

### b. Protocol 与类型体系修正

| 文件 | 改动 |
|------|------|
| `throttled/types.py` | `do()` → `tuple[int \| float, ...]`；移除 AtomicAction Protocol 的 `__init__` |
| `throttled/store/base.py` | `BaseAtomicAction.do()` → `tuple[int \| float, ...]`；`get_client()` 返回类型 |
| `throttled/asyncio/store/base.py` | async `BaseAtomicAction.do()` 同步修改 |
| 所有 rate limiter CoreMixin + concrete | `_DEFAULT_ATOMIC_ACTION_CLASSES` 从 `list` → `Sequence` |

### c. async 侧联合类型窄化

| 文件 | 改动 |
|------|------|
| `throttled/asyncio/rate_limiter/base.py` | `_store: _AsyncStoreP`；`_atomic_actions: dict[..., _AsyncAtomicActionP]` |
| `throttled/asyncio/store/memory.py` | `_get_lock` → `@classmethod`；`lock: _AsyncLockP` |
| async rate limiter concrete 类（5 个） | `no-any-return` 修复（Redis script 返回值 cast）；`int \| float → int` 赋值修复 |
| `throttled/asyncio/rate_limiter/__init__.py` | 修复 `GCRARateLimiterCoreMixin` 导出 |

### d. 验证

1. `uv run mypy --strict throttled/` → 0 errors
2. `uv run ruff check throttled/` → 0 errors
3. `uv run pytest` → 全部通过

## 0x04 验收与验证

- mypy --strict 0 errors
- 无 `# type: ignore` 注释
- ruff check 通过
- pytest 全部通过
- 不改变公共 API 签名

## 0x05 实施进展（表格）

| 时间 | 结论调整概要 | 改动 |
|------|------|------|
| | | |

## 0x06 参考

- [排障经验：同步异步共用 Mixin 的泛型类型窄化](../../troubleshooting/generic-mixin-type-narrowing.md)
- [mypy — Protocols and structural subtyping](https://mypy.readthedocs.io/en/stable/protocols.html)
- [PEP 544 — Protocols](https://peps.python.org/pep-0544/)

## 0x07 版本锚点

- 分支：`fix/260406_mypy_strict`
- PR：待定
