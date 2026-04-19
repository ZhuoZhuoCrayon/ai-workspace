---
title: mypy strict 模式合规改造方案
tags: [throttled-py, typing, mypy, strict, generics]
issue: ./README.md
description: 泛型化重构消除 cast(Any) 与联合类型泄漏，达成 mypy --strict 全绿且零 type:ignore，运行时完全兼容
created: 2026-04-06
updated: 2026-04-18
---

# mypy strict 模式合规改造 —— 实施方案

基于 [README.md](./README.md) 制定。

关键背景：

- 本方案为**现行版本**，用泛型化重构彻底取代一轮「属性窄化 + 集中 accessor」。
- 一轮（2026-04-07）已合入 [PR #145](https://github.com/ZhuoZhuoCrayon/throttled-py/pull/145)，仍遗留结构性缺陷。
- 二轮（2026-04-18）沿用旧分支 `fix/260406_mypy_strict` 续推，两轮实施记录并存于 [0x07 进展](#0x07-进展)。

## 0x01 现状

### a. 一轮落地后基线

- `uv run mypy --strict throttled/` 0 errors，`ruff` 与 `pytest` 全绿（PR #145）。
- 基础设施修复已完成且仍然适用，二轮无需重做，详见 [0x07.a](#a-一轮基线-2026-04-07)。

保留项清单：

| 位点 | 修复 |
|------|------|
| `Quota` dataclass | 改为 `field(init=False)` |
| `_DEFAULT_ATOMIC_ACTION_CLASSES` | 从 `list` 收紧为 `Sequence` |
| 分支变量 `redef` | 统一提前声明 |
| `utils / redis_pool / exceptions` | 纯注解补齐 |

### b. 一轮遗留的结构性缺陷

以下问题二轮必须解决：

| 编号 | 缺陷 | 说明 |
|------|------|------|
| 1 | `cast(Any, action_cls)(backend=...)` | `BaseStore.make_atomic` 绕 Protocol 构造限制走 `Any`，丢失全部类型信息 |
| 2 | `_get_atomic_action` 集中 cast | 10 条 `_limit / _peek` 路径靠它强制窄化 dict 值，`dict` invariance 的补丁 |
| 3 | async 继承 sync CoreMixin 的类型谎言 | async atomic action 复用 sync `__init__(backend: RedisStoreBackend)`，`lock` 还要 `cast("AsyncLockP", ...)` |
| 4 | `MemoryStoreBackend.lock` 的 double cast | `_AsyncLockP` 属性窄化 + 运行时 cast，根因是 `BaseMemoryStoreBackend.lock` 未参数化 |
| 5a | `RedisStoreBackend` 继承错误 | `throttled/store/redis.py` 漏继承 `BaseRedisStoreBackend`，`get_client()` 运行时必 `AttributeError` |
| 5b | `get_client` 语法错误 | `BaseStoreBackend.get_client` 体内 `raise self._client` 应为 `return` |

## 0x02 设计原则

### a. 两轴

- **轴 A — backend 作为类型参数**：`AtomicAction` 与 `Store` 以 `_BackendT bound=BaseStoreBackend[Any]` 参数化。
- **轴 A 效果**：具体 backend（sync Redis / async Redis / sync Memory / async Memory）在 concrete 层自动窄化 `self._backend`。
- **轴 B — sync/async 平行层级**：拒绝用 TypeVar 抽象 `def` 与 `async def` 的差异。
- **轴 B 形态**：sync 与 async 各自保有完整基类树，`throttled.store.BaseStore` 与 `throttled.asyncio.store.BaseStore` 是**同名两个不同类**。
- **轴 B 共享面**：仅共享纯常量容器与纯函数 helper（Lua 脚本字符串、Memory 侧 `_do` classmethod）。

### b. 决策与取舍

| 决策 | 原因 |
|------|------|
| `BaseStore.make_atomic` 使用方法级 TypeVar | 必须与 `StoreForLimiterP.make_atomic` 逐位同签名，mypy 才认可结构化子类 |
| 放弃 Store 与 Action backend 的类型级配对 | 同一算法的 `_DEFAULT_ATOMIC_ACTION_CLASSES` 并列 Redis 与 Memory 条目，由 `STORE_TYPE` 运行时过滤 |
| 算法 CoreMixin 不继承 Generic Mixin | 改为纯 mixin，避免每个 CoreMixin 都要填 `[Any, Any]` 与 MRO 二义 |
| Registry 每侧独立 dict | sync / async 的 `_RATE_LIMITERS` 各自声明，避免共享 dict 导致类型泄漏 |
| 保留**唯一**允许的 `Any` | `dict[str, type[Any]]` 一处，由 `Generic[_LimiterT]` 的 `get()` 返回类型兜底 |
| `cast` 预算 ≤ 5 | 仅允许出现在 Lua 元组形状窄化，行内必须注释 `# Lua script tuple shape narrowing` |

## 0x03 架构

### a. 类型契约（`throttled/types.py`）

统一维护跨 sync/async 的共用 Protocol：

```python
_A_ForStore = TypeVar("_A_ForStore")

class StoreForLimiterP(Protocol):
    TYPE: str
    def make_atomic(self, action_cls: type[_A_ForStore]) -> _A_ForStore: ...
```

要点：

- `_A_ForStore` 不加 bound，避免撕裂 sync 与 async 两侧的 `BaseAtomicAction`。
- 运行时由 `STORE_TYPE` 过滤加 `action_cls(backend=self._backend)` 的直接调用兜底。
- `AtomicActionP` 与 `StoreP` 作为 deprecation-friendly 别名保留，内部代码不再使用。

### b. 三层基类（Store 侧）

sync `throttled/store/base.py` 与 async `throttled/asyncio/store/base.py` 对称定义以下骨架：

```python
_BackendT = TypeVar("_BackendT", bound="BaseStoreBackend[Any]")
_A = TypeVar("_A")  # method-level, same shape as StoreForLimiterP._A_ForStore

class BaseAtomicActionMixin(Generic[_BackendT]):
    TYPE: AtomicActionTypeT = ""
    STORE_TYPE: str = ""
    _backend: _BackendT
    def __init__(self, backend: _BackendT) -> None:
        self._backend = backend

class BaseAtomicAction(BaseAtomicActionMixin[_BackendT], abc.ABC, Generic[_BackendT]):
    @abc.abstractmethod
    def do(self, keys, args) -> tuple[int | float, ...]: ...

class BaseStore(BaseStoreMixin, abc.ABC, Generic[_BackendT]):
    _backend: _BackendT
    def make_atomic(self, action_cls: type[_A]) -> _A:
        return action_cls(backend=self._backend)
```

sync 侧 `do` 为 `def`，async 侧为 `async def`，其他签名对称。

### c. CoreMixin 三层拆分（算法侧）

5 个算法（`TokenBucket / FixedWindow / SlidingWindow / LeakingBucket / GCRA`）乘 2 backend，全部按此结构重写。

层次：

| 层 | 继承 | 职责 |
|------|------|------|
| 常量容器 | 无基类 | 承载 `TYPE`、`STORE_TYPE`、`SCRIPTS`（仅 Redis 用） |
| sync CoreMixin | `(常量容器, BaseAtomicActionMixin[SyncBackend])` | Redis 在 `__init__` 注册 `_script: SyncScript` |
| async CoreMixin | `(常量容器, BaseAtomicActionMixin[AsyncBackend])` | 注册 `_script: AsyncScript` |
| concrete | `(CoreMixin, BaseAtomicAction[SameBackend])` | 只定义 `do()` |

Memory 侧补充：

- `_do` classmethod 写在 sync 文件的 CoreMixin 上，参数泛化为 `_MemBackendT bound=BaseMemoryStoreBackend[Any]`。
- 仅使用 `BaseMemoryStoreBackend` 的方法，sync 与 async concrete 都能复用。

GCRA 补充：

- `PeekAtomicAction` 通过 `(PeekScripts, LimitAtomicAction)` MRO 覆盖 `SCRIPTS`。
- `do()` 与 `__init__` 从 Limit 继承，backend 参数自动对齐。

### d. RateLimiter 层

`throttled/rate_limiter/base.py`（以及 async 镜像）核心骨架：

```python
from ..types import StoreForLimiterP

_StoreT = TypeVar("_StoreT", bound=StoreForLimiterP)
_ActionT = TypeVar("_ActionT", bound="BaseAtomicAction[Any]")

class BaseRateLimiterMixin(Generic[_StoreT, _ActionT], ABC):
    _store: _StoreT
    _atomic_actions: dict[AtomicActionTypeT, _ActionT]
    def _register_atomic_actions(self, classes: Sequence[type[_ActionT]]) -> None:
        for action_cls in (*self._default_atomic_action_classes(), *classes):
            if action_cls.STORE_TYPE != self._store.TYPE:
                continue
            self._atomic_actions[action_cls.TYPE] = self._store.make_atomic(action_cls)

class BaseRateLimiter(
    BaseRateLimiterMixin["BaseStore[Any]", "BaseAtomicAction[Any]"],
    ABC, metaclass=RateLimiterMeta,
): ...
```

要点：

- 5 个算法 CoreMixin（`TokenBucketRateLimiterCoreMixin` 等）改为**纯 mixin**，不继承 `BaseRateLimiterMixin`。
- concrete 仍是 `(AlgoCoreMixin, BaseRateLimiter)`，`_store` 与 `_atomic_actions` 经 MRO 从 `BaseRateLimiterMixin` 获得。
- `_DEFAULT_ATOMIC_ACTION_CLASSES` 类型收窄为 `Sequence[type["BaseAtomicAction[Any]"]]`。
- `_limit` 与 `_peek` 内对 `self._atomic_actions[TYPE].do(...)` 做**唯一**允许的 cast。
- cast 形态：`cast("tuple[int, int, float, float]", ...)`，窄化为算法定宽元组，并行内注释 `# Lua script tuple shape narrowing`。

### e. Registry 与 Throttled 层

Registry（sync 与 async 镜像）：

```python
class RateLimiterRegistry(Generic[_LimiterT]):
    _NAMESPACE: ClassVar[str] = ""
    _RATE_LIMITERS: ClassVar[dict[str, type[Any]]] = {}
    @classmethod
    def get(cls, _type: RateLimiterTypeT) -> type[_LimiterT]:
        return cls._RATE_LIMITERS[cls.get_register_key(_type)]

class SyncRateLimiterRegistry(RateLimiterRegistry["BaseRateLimiter"]):
    _NAMESPACE = "sync"
    _RATE_LIMITERS = {}   # 重新声明，避免跨 namespace 共享

class AsyncRateLimiterRegistry(RateLimiterRegistry["AsyncBaseRateLimiter"]):
    _NAMESPACE = "async"
    _RATE_LIMITERS = {}
```

Throttled：

```python
class BaseThrottledMixin(Generic[_LimiterT, _HookT, _StoreT]):
    _DEFAULT_GLOBAL_STORE: _StoreT | None = None
    _REGISTRY_CLASS: type[RateLimiterRegistry[_LimiterT]] | None = None
    _store: _StoreT
    _limiter_cls: type[_LimiterT]
```

- sync `BaseThrottled(BaseThrottledMixin["BaseRateLimiter", "Hook", "BaseStore[Any]"], ABC)`，async 对称。
- `_DEFAULT_GLOBAL_STORE` 改为纯类属性，TypeVar 不可入 `ClassVar`。
- `self._limiter_cls = self._REGISTRY_CLASS.get(...)` 返回精确类型，后续实例化直接匹配。
- `__init__` 与 `limiter` 内的两处 cast 全部删除。

## 0x04 实施步骤

沿用旧分支 `fix/260406_mypy_strict` 续做，不新建分支。

执行约束：

- 本地已有部分改动，按本节顺序逐组续推。
- 每组完成后独立跑 `mypy --strict` 局部验证，再进入下一组。

### a. 修前置 bug 与基础契约

| 文件 | 改动 |
|------|------|
| `throttled/types.py` | 新增 `StoreForLimiterP`，标注 `AtomicActionP` 与 `StoreP` 为 deprecated alias |
| `throttled/store/base.py` | [1] `BaseStoreBackend.get_client` 将 `raise self._client` 改为 `return`<br />[2] 引入 `_BackendT` 与 `_A`<br />[3] `BaseAtomicActionMixin / BaseAtomicAction / BaseStore` 改为 Generic，`make_atomic` 使用方法级 TypeVar |
| `throttled/store/redis.py` | `class RedisStoreBackend(BaseRedisStoreBackend[SyncRedisClientP])` 修正继承链 |
| `throttled/store/memory.py` | `BaseMemoryStoreBackend` 参数化 `_LockT`，sync `MemoryStoreBackend` 具象化 `_LockT = SyncLockP` |
| `throttled/asyncio/store/base.py` | 同 sync 对称改造，`do` 为 `async def` |
| `throttled/asyncio/store/redis.py` | async `RedisStoreBackend` 具象化 `_ClientT = AsyncRedisClientP` |
| `throttled/asyncio/store/memory.py` | async `MemoryStoreBackend` 具象化 `_LockT = AsyncLockP` |

### b. 算法层重写

每个算法文件按 [0x03.c](#c-coremixin-三层拆分算法侧) 的四段式改写。成对处理：

| sync 文件 | async 文件 | 备注 |
|------|------|------|
| `token_bucket.py` | `asyncio/token_bucket.py` | |
| `fixed_window.py` | `asyncio/fixed_window.py` | |
| `sliding_window.py` | `asyncio/sliding_window.py` | |
| `leaking_bucket.py` | `asyncio/leaking_bucket.py` | |
| `gcra.py` | `asyncio/gcra.py` | 含 Peek 多重继承 |

每个文件产出：

- 常量容器 1。
- CoreMixin 1，sync 文件承载 sync CoreMixin，async 文件承载 async CoreMixin。
- concrete AtomicAction N，N 为 1 或 2（GCRA 含 Peek）。
- RateLimiter CoreMixin 1，纯 mixin。
- concrete RateLimiter 1。

**不允许出现**：

- `cast("SyncLockP", ...)` 与 `cast("AsyncLockP", ...)`。
- `cast("AsyncRedisClientP", ...)` 或其他 client 窄化 cast。
- `cast(Any, ...)`。
- `self._backend: XxxStoreBackend = backend` 的类型谎言 redundant 赋值。
- async 文件 import sync CoreMixin 作为基类。

**允许出现**：

- `cast("tuple[int, ...]", self._atomic_actions[TYPE].do(...))`，Lua 元组窄化，必须附注释。
- `cast("int | None", backend.get(key))`，SlidingWindow Memory 读 `OrderedDict` 的形状窄化，已有。

### c. RateLimiter 与 Registry 与 Throttled

| 文件 | 改动 |
|------|------|
| `throttled/rate_limiter/base.py` | [1] `BaseRateLimiterMixin` 改 `Generic[_StoreT, _ActionT]`<br />[2] `_store` 与 `_atomic_actions` 与 `_register_atomic_actions` 去 cast<br />[3] `RateLimiterRegistry` 改 `Generic[_LimiterT]`<br />[4] 新增 `SyncRateLimiterRegistry` 并声明独立 dict |
| `throttled/asyncio/rate_limiter/base.py` | 对称，新增 `AsyncRateLimiterRegistry` |
| `throttled/rate_limiter/<algo>.py` | [1] 删除 `BaseRateLimiterMixin` 继承<br />[2] `_DEFAULT_ATOMIC_ACTION_CLASSES` 类型改 `Sequence[type["BaseAtomicAction[Any]"]]`<br />[3] `_get_atomic_action` 调用点回退为 `self._atomic_actions[TYPE].do(...)` 后做 Lua 元组 cast |
| `throttled/asyncio/rate_limiter/<algo>.py` | 对称 |
| `throttled/throttled.py` | [1] `BaseThrottledMixin` 增 `_StoreT`<br />[2] `_DEFAULT_GLOBAL_STORE` 改纯类属性<br />[3] `_REGISTRY_CLASS` 泛型化<br />[4] 删除 `__init__` 与 `limiter` 内的两处 cast |
| `throttled/asyncio/throttled.py` | 对称 |

### d. 配置与守护

`pyproject.toml` 参考片段：

```toml
[tool.mypy]
python_version = "3.10"
strict = true
warn_unused_ignores = true
files = ["throttled"]

[[tool.mypy.overrides]]
module = ["tests.*", "benchmarks.*"]
ignore_errors = true
```

| 文件 | 改动 |
|------|------|
| `pyproject.toml` | 保留 `strict = true`，新增 `warn_unused_ignores = true`，`tests.*` 与 `benchmarks.*` 放宽到 `ignore_errors` |
| `.pre-commit-config.yaml` | `mypy` 钩子作用域覆盖 `throttled/` 全量 |
| CI workflow | `uv run mypy --strict throttled` 作为独立 job |

## 0x05 验收

- `uv run mypy --strict throttled` 0 errors 与 0 warnings。
- `uv run ruff check throttled` 0 errors。
- `uv run pytest` 全绿（sync 与 async，真实 Redis 可选跳过）。
- `rg "cast\(" throttled/` 留存 ≤ 5 处，全部为 Lua 元组形状窄化且有行内注释。
- `rg "# type: ignore" throttled/` = 0。
- 实例化链路冒烟共 20 组：sync 与 async 乘 Memory 与 Redis 乘 5 算法。
- 每组验证 `Throttled(...).limit(...)` 与 `await Throttled(...).limit(...)` 不抛错（真实 Redis 依赖可跳过）。

## 0x06 风险与约束

| 维度 | 取舍 | 兜底 |
|------|------|------|
| CoreMixin 膨胀 | 5 算法乘 2 backend 的 CoreMixin 由 1 份裂成 sync / async 各 1 份，约 20 行新增 | 换来类型精确与消除类型谎言，收益远大于成本 |
| `Registry._RATE_LIMITERS` 单处 `Any` | `ClassVar[dict[str, type[Any]]]` 中的 `Any` 是全方案唯一保留项 | `Generic[_LimiterT]` 的 `get()` 返回类型在调用侧自动窄化 |
| 放弃 Store 与 Action backend 的类型级配对 | 由 `StoreForLimiterP.make_atomic` 与 `BaseStore.make_atomic` 同用不加 bound 的方法级 TypeVar | 运行时 `STORE_TYPE != self._store.TYPE` 过滤兜底，既有行为不变 |
| sync Redis 首次真正可用 | 修正 `RedisStoreBackend` 继承链与 `get_client` 的 return 缺失 | 无兼容风险，既有代码在该路径上本就会崩溃 |
| 运行时兼容边界 | 用户 import 路径与类名与实例化写法与方法名全部不变，类型签名可调 | `AtomicActionP` 与 `StoreP` 保留为 deprecation-friendly 别名 |

## 0x07 进展

### a. 一轮基线（2026-04-07）

| 时间 | 对应设计片段 | 结论调整概要 | 改动 / 验证 |
|------|------|------|------|
| `2026-04-07` | `0x01.a` 与 `0x01.b` | [1] 采用属性窄化加集中 accessor 加 `cast(Any, action_cls)` 绕 Protocol 构造限制<br />[2] 识别出 3 条结构性缺陷，见 [0x01.b](#b-一轮遗留的结构性缺陷) | [1] 提交 `20eb1ee` `5639a49` `ad34a00`<br />[2] PR [#145](https://github.com/ZhuoZhuoCrayon/throttled-py/pull/145)<br />[3] `mypy --strict` 0 errors，`ruff` 与 `pytest` 与 `pre-commit` 全绿 |

二轮沿用的基础修复：

| 位点 | 修复 |
|------|------|
| `Quota` dataclass | `field(init=False)` |
| `_DEFAULT_ATOMIC_ACTION_CLASSES` | 从 `list` 收紧为 `Sequence[...]` |
| 分支变量 `redef` | 统一提前声明 |
| `utils.py` 与 `redis_pool.py` | 注解补齐 |
| Protocol | 移除 `__init__` |

### b. 二轮泛型化（2026-04-18 起）

| 时间 | 对应设计片段 | 结论调整概要 | 改动 / 验证 |
|------|------|------|------|
| `2026-04-18` | `0x02` 与 `0x03` 全量 | [1] 完成顶向下校对，识别 3 个设计漏洞（Protocol 结构匹配，CoreMixin MRO，Registry dict 共享）<br />[2] 识别 2 个既有 bug（sync `RedisStoreBackend` 继承，`get_client` 的 return 缺失）<br />[3] 分支沿用 `fix/260406_mypy_strict`，不新建分支 | [1] 方案定稿<br />[2] commit 与 PR 链接完工后回填 |

## 0x08 参考

- [排障经验：同步异步共用 Mixin 的泛型类型窄化](../../troubleshooting/generic-mixin-type-narrowing.md)
- [mypy — Protocols and structural subtyping](https://mypy.readthedocs.io/en/stable/protocols.html)
- [PEP 544 — Protocols](https://peps.python.org/pep-0544/)

## 0x09 版本锚点

- 分支：`fix/260406_mypy_strict`，沿用旧分支。
- 一轮：已合入 [PR #145](https://github.com/ZhuoZhuoCrayon/throttled-py/pull/145)。
- 二轮：续接在同分支 HEAD，落地 commit 与 PR 链接完工后回填。
