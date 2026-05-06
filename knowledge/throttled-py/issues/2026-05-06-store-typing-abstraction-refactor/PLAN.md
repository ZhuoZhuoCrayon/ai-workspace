---
title: Store 类型抽象边界优化方案
tags: [throttled-py, typing, store, abstraction, public-api, httpx]
issue: ./README.md
description: 对照 HTTPX transport 设计，拆分 BaseStore 公共能力边界与 backend-bound 实现边界
created: 2026-05-06
updated: 2026-05-06
---

# Store 类型抽象边界优化 —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 调研与约束

### a. 当前现象

PR #159 把运行时配对关系放进泛型继承链后，`BaseStore` 成为 `BaseStore[_BackendT]`。

这让普通用户想表达“返回一个同步 store”时必须同时回答“这个 store 绑定哪个 backend”。

当前 `mypy --strict` 复现结果：

| 用户写法 | 类型检查结果 | 结论 |
|------|------|------|
| `_get_store() -> BaseStore` | `Missing type arguments for generic type "BaseStore"` | 裸 `BaseStore` 不可用。 |
| `_get_store() -> BaseStore[BaseStoreBackend[object]]` | `RedisStore` / `MemoryStore` 返回值不兼容 | 泛型不变性暴露到用户侧。 |
| `_get_store() -> BaseStore[types.StoreBackendP]` | `RedisStore` / `MemoryStore` 返回值不兼容 | backend 协议不能自然代表具体 store。 |
| `_get_store() -> types.SyncStoreP` | 通过 | 能绕过当前报错，但公共 API 语义不直观。 |
| `Throttled(store=store)` | `got Module; expected SyncStoreP` | 示例变量名会掩盖真正的 store 实例边界。 |

这些现象说明：`SyncStoreP` 只是绕过当前类型问题的临时出口。

如果用户侧仍必须理解协议类型，`BaseStore` 就还没有真正回到 public boundary。

### b. HTTPX transport 调研

HTTPX 的 transport 设计提供了清晰对照。

```mermaid
flowchart TD
    BaseTransport["BaseTransport"]
    AsyncBaseTransport["AsyncBaseTransport"]
    HTTPTransport["HTTPTransport"]
    AsyncHTTPTransport["AsyncHTTPTransport"]
    WSGITransport["WSGITransport"]
    ASGITransport["ASGITransport"]
    MockTransport["MockTransport"]
    Client["Client"]
    AsyncClient["AsyncClient"]
    Pool["_pool: httpcore.*"]
    App["app: WSGI / ASGI"]
    Handler["handler"]

    BaseTransport --> HTTPTransport
    BaseTransport --> WSGITransport
    BaseTransport --> MockTransport
    AsyncBaseTransport --> AsyncHTTPTransport
    AsyncBaseTransport --> ASGITransport
    AsyncBaseTransport --> MockTransport
    Client --> BaseTransport
    AsyncClient --> AsyncBaseTransport
    HTTPTransport --> Pool
    AsyncHTTPTransport --> Pool
    WSGITransport --> App
    ASGITransport --> App
    MockTransport --> Handler
```

关键事实：

- `BaseTransport` 与 `AsyncBaseTransport` 是 public API，且没有底层 backend 泛型。
- `T` / `A` 只用于 context manager 返回子类自身，不表达 `httpcore` backend 配对。
- `HTTPTransport` 继承 `BaseTransport`，内部根据配置选择 `httpcore.ConnectionPool`、
  `httpcore.HTTPProxy` 或 `httpcore.SOCKSProxy`，这些对象统一藏在 `_pool`。
- `Client.__init__` 接收 `transport: BaseTransport | None`，`mounts` 也是 `Mapping[str, BaseTransport | None]`。
- `WSGITransport` 与 `ASGITransport` 分别继承 sync / async base，应用协议放在构造参数和实例属性。
- `MockTransport` 同时继承 sync / async base，因为它显式实现了两套请求方法。

HTTPX 的抽象原则：

```text
public base class = 调用方需要的能力边界
concrete transport = 具体运行时适配器
private attribute = 底层 backend / app / handler
```

对应到 throttled-py，`BaseStore` 不应携带具体 backend 类型参数。

backend 配对应留在实现辅助层或私有属性层。

### c. throttled-py 当前对象链路

当前同步 store 链路：

```mermaid
flowchart TD
    ClientT["_ClientT"] --> BaseStoreBackend["BaseStoreBackend[_ClientT]"]
    BaseStoreBackend --> BaseMemoryStoreBackend["BaseMemoryStoreBackend"]
    BaseStoreBackend --> BaseRedisStoreBackend["BaseRedisStoreBackend[RedisClientT]"]
    BaseMemoryStoreBackend --> MemoryStoreBackend["MemoryStoreBackend"]
    BaseRedisStoreBackend --> RedisStoreBackend["RedisStoreBackend"]
    BackendT["_BackendT"] --> BaseStore["BaseStore[_BackendT]"]
    MemoryStoreBackend --> MemoryStore["MemoryStore(BaseStore[MemoryStoreBackend])"]
    RedisStoreBackend --> RedisStore["RedisStore(BaseStore[RedisStoreBackend])"]
    BackendT --> BaseAtomicAction["BaseAtomicAction[_BackendT]"]
    BaseAtomicAction --> RedisAction["RedisLimitAtomicAction"]
    BaseAtomicAction --> MemoryAction["MemoryLimitAtomicAction"]
    MemoryStore --> SyncStoreP["types.SyncStoreP"]
    RedisStore --> SyncStoreP
```

当前设计把三个层级压在 `BaseStore[_BackendT]` 上：

- **公共能力边界**：用户期待 `BaseStore` 表达“同步 store”。
- **实现继承基类**：`MemoryStore` / `RedisStore` 复用抽象方法、校验和包装机制。
- **backend 配对载体**：`make_atomic()` 用 `_backend: _BackendT` 构造匹配的 AtomicAction。

这三个职责的稳定性不同：公共能力边界应该稳定且简单。

backend 配对是实现细节，应该尽量晚暴露。

### d. 类型绕行点

当前绕行不是单点报错，而是抽象边界失衡后的连锁反应：

- `BaseStore` 裸用失败，测试和 fixture 只能写 `BaseStore[Any]`。
- 用户侧工厂必须写 `types.SyncStoreP`，但文档注释仍写 `throttled.store.BaseStore`。
- `BaseThrottledMixin` 用 `_StoreT` 横跨 sync / async store，通过注册表取得 limiter 类的位置需要 `cast`。
- `BaseAtomicAction[_BackendT]` 将 action 能力边界和 backend 绑定放在同一个 public 名称上。
- `StoreP = SyncStoreP | AsyncStoreP` 虽标记 deprecated，但仍参与 `_StoreT` 约束。

## 0x02 架构设计

### a. 分层模型

目标结构采用 HTTPX 风格：public base class 表达能力边界，backend-bound helper 表达实现配对。

```mermaid
flowchart TD
    BaseStore["BaseStore<br />public sync store boundary"]
    AsyncBaseStore["asyncio.store.BaseStore<br />public async store boundary"]
    BackendBoundStore["BackendBoundStore[_BackendT]"]
    AsyncBackendBoundStore["async BackendBoundStore[_BackendT]"]
    BaseStoreBackend["BaseStoreBackend[_ClientT]"]
    MemoryBackend["MemoryStoreBackend"]
    RedisBackend["RedisStoreBackend"]
    MemoryStore["MemoryStore"]
    RedisStore["RedisStore"]
    AsyncMemoryStore["async MemoryStore"]
    AsyncRedisStore["async RedisStore"]
    SyncLimiter["sync RateLimiter"]
    AsyncLimiter["async RateLimiter"]
    Throttled["throttled.Throttled"]
    AsyncThrottled["throttled.asyncio.Throttled"]

    BaseStore --> BackendBoundStore
    AsyncBaseStore --> AsyncBackendBoundStore
    BaseStoreBackend --> MemoryBackend
    BaseStoreBackend --> RedisBackend
    BackendBoundStore --> MemoryStore
    BackendBoundStore --> RedisStore
    MemoryBackend --> MemoryStore
    RedisBackend --> RedisStore
    MemoryStore --> SyncLimiter
    RedisStore --> SyncLimiter
    AsyncBackendBoundStore --> AsyncMemoryStore
    AsyncBackendBoundStore --> AsyncRedisStore
    AsyncMemoryStore --> AsyncLimiter
    AsyncRedisStore --> AsyncLimiter
    SyncLimiter --> Throttled
    AsyncLimiter --> AsyncThrottled
```

这张图只表达职责关系，不代表具体文件改动。

### b. 边界不变量

本方案的核心判断是分离两种类型问题：public API 回答“调用方可以把它当作什么”，内部实现回答“构造时绑定了什么”。

| 层级 | 应表达的语义 | 不应表达的语义 |
|------|--------------|----------------|
| `BaseStore` | 同步 store 能力边界 | 具体 backend 类型 |
| `asyncio.store.BaseStore` | 异步 store 能力边界 | 同步 store 能力或具体 backend 类型 |
| `BackendBoundStore[_BackendT]` | 内建 store 与 backend 的构造配对 | 用户侧通用返回类型 |
| `BaseStoreBackend[_ClientT]` | 底层 client 与异常族 | limiter 所需 store 能力 |
| `StoreP` | 废弃兼容别名 | public API 或核心泛型边界 |

稳定不变量：

- `BaseStore`：非泛型公共同步 store 边界。
- `asyncio.store.BaseStore`：非泛型公共异步 store 边界。
- `BackendBoundStore[_BackendT]`：内建 store 使用的实现辅助层，负责 `_backend` 和 `make_atomic()`。
- `BaseStoreBackend[_ClientT]`：继续表达底层 client 类型，不向普通 store 工厂泄漏。
- `StoreP`：仅作为废弃兼容别名处理，不再参与 public API 或核心泛型约束。

### c. 用户侧类型语义

用户侧 store 工厂只需要表达“返回同步 store”。

它不应该暴露 Redis、Memory 或 backend 类型参数。

目标写法：

```python
def _get_store(use_redis: bool) -> BaseStore:
    if use_redis:
        return store.RedisStore(server="redis://127.0.0.1:6379/0")
    return store.MemoryStore()
```

`Throttled(store=_get_store())` 应直接通过 `BaseStore` 接收，而不是依赖 `BaseStore` 结构上满足 `SyncStoreP`。

这条语义保留一种官方扩展方式：

- 同步自定义 store 继承 `throttled.store.BaseStore`。
- 异步自定义 store 继承 `throttled.asyncio.store.BaseStore`。
- 不继承基类的结构化 store 不再作为推荐扩展路径进入核心 API。

### d. AtomicAction 语义

`BaseAtomicAction` 也应采用同样原则：public 名称表达 action 能力。

backend 配对放到辅助层。

```mermaid
flowchart TD
    BaseAtomicAction["BaseAtomicAction<br />public action boundary"]
    BackendBoundAtomicAction["BackendBoundAtomicAction[_BackendT]"]
    RedisAtomicAction["RedisLimitAtomicAction"]
    MemoryAtomicAction["MemoryLimitAtomicAction"]
    Backend["Store backend"]

    BaseAtomicAction --> BackendBoundAtomicAction
    BackendBoundAtomicAction --> RedisAtomicAction
    BackendBoundAtomicAction --> MemoryAtomicAction
    Backend --> BackendBoundAtomicAction
```

AtomicAction 的关键边界：

- `BaseAtomicAction` 声明 `TYPE`、`STORE_TYPE` 和同步 `do()`。
- `BackendBoundAtomicAction[_BackendT]` 持有 `_backend` 并提供构造器。
- async 侧 `BaseAtomicAction` 声明 async `do()`，同样由 async backend-bound helper 持有 `_backend`。
- `SyncAtomicActionP` / `AsyncAtomicActionP` 保留，用于 limiter 内部字典和额外 action 扩展。

这样 custom action 的文档可以说“继承 `BaseAtomicAction` 并实现 `do()`”，而不是要求用户理解 `_BackendT`。

### e. Throttled 共享边界

`Throttled` 的共享层只承载配置与计算辅助。

Store、Limiter 和 Hook 的模式差异在 sync / async 具体层落定。

```mermaid
classDiagram
    class BaseThrottledShared {
        +key
        +timeout
        +_quota
        +_cost
        +_get_key()
        +_get_timeout()
        +_get_wait_time()
    }
    class SyncBaseThrottled {
        +BaseStore _store
        +BaseRateLimiter _limiter
        +Hook[] _hooks
        +BaseRateLimiter limiter
        +_make_limiter() BaseRateLimiter
    }
    class AsyncBaseThrottled {
        +AsyncBaseStore _store
        +AsyncBaseRateLimiter _limiter
        +AsyncHook[] _hooks
        +AsyncBaseRateLimiter limiter
        +_make_limiter() AsyncBaseRateLimiter
    }

    BaseThrottledShared <|-- SyncBaseThrottled
    BaseThrottledShared <|-- AsyncBaseThrottled
```

图中第三方依赖只作为成员类型出现，不再画成独立节点。

`AsyncBaseStore` 指 `throttled.asyncio.store.BaseStore`。

判定点：`_make_limiter()` 和 `limiter` 属于组合边界，不属于共享配置层。

## 0x03 开发方案

### a. Store 公共边界

Store 公共边界负责“用户和 limiter 能调用什么”。

它只声明命令、`TYPE` 和 `make_atomic()`，不持有 `_backend`。

**（1）协议落点**

| 问题 | 处理方式 |
|------|----------|
| 在哪声明 | [1] 同步声明在 `throttled/store/base.py` 的 `BaseStore`<br />[2] 异步声明在 `throttled/asyncio/store/base.py` 的 `BaseStore` |
| 上层如何取用 | [1] 用户、文档和 store 工厂使用 `BaseStore`<br />[2] `Throttled` / sync limiter 通过同步 `BaseStore` 接收能力<br />[3] async `Throttled` / async limiter 通过 async `BaseStore` 接收能力 |
| 如何收敛 | `BaseStore` 只保留抽象方法，backend 绑定下沉到 backend-bound helper。 |

**（2）最小结构**

```python
class BaseStore(BaseStoreMixin, abc.ABC):
    TYPE: str = ""

    @abc.abstractmethod
    def exists(self, key: types.KeyT) -> bool: ...

    @abc.abstractmethod
    def make_atomic(self, action_cls: type[_ActionT]) -> _ActionT: ...
```

async 侧保持同构，但命令方法使用 `async def`。

**（3）实现约束**

- 不把 `_BackendT` 改成 `Any` 后继续挂在 `BaseStore`。
- 不要求用户写 `BaseStore[Any]` 或 `BaseStore[StoreBackendP]`。
- 不通过 `cast("BaseStore", ...)` 修复示例。
- 不把 sync / async store 合并成同一个 `BaseStore`。
- 不再新增 `SyncStoreP` / `AsyncStoreP` 引用。

### b. Backend-bound 实现层

Backend-bound 实现层负责“内建 store 如何构造匹配 action”。

这层可以是 public helper，也可以用下划线前缀表达内部用途。

**（1）协议落点**

| 问题 | 处理方式 |
|------|----------|
| 在哪声明 | [1] 同步 helper 位于 `throttled/store/base.py`<br />[2] 异步 helper 位于 `throttled/asyncio/store/base.py` |
| 上层如何取用 | `MemoryStore` / `RedisStore` 继承 helper，普通用户不需要直接标注 helper 类型。 |
| 如何收敛 | 默认 `make_atomic()` 只在 helper 中实现，统一从 `_backend` 构造 action。 |

**（2）最小结构**

```python
class BackendBoundStore(BaseStore, Generic[_BackendT]):
    _backend: _BackendT

    def make_atomic(self, action_cls: type[_ActionT]) -> _ActionT:
        factory: Callable[..., _ActionT] = action_cls
        return factory(backend=self._backend)
```

**（3）迁移规则**

| 对象 | 当前继承 | 目标继承 | 说明 |
|------|----------|----------|------|
| `MemoryStore` | `BaseStore[MemoryStoreBackend]` | `BackendBoundStore[MemoryStoreBackend]` | 保留锁、LRU 与过期语义。 |
| `RedisStore` | `BaseStore[RedisStoreBackend]` | `BackendBoundStore[RedisStoreBackend]` | 保留连接工厂与 Redis 命令转换。 |
| async `MemoryStore` | async `BaseStore[MemoryStoreBackend]` | async `BackendBoundStore[MemoryStoreBackend]` | 保留 async lock 语义。 |
| async `RedisStore` | async `BaseStore[RedisStoreBackend]` | async `BackendBoundStore[RedisStoreBackend]` | 保留 async Redis client 协议。 |

**（4）包装机制约束**

`BaseStoreMixin._WRAPPED_METHOD_NAMES` 继续声明 `make_atomic()` 是包装边界。

如果包装逻辑依赖 `__init_subclass__`，需要确认 helper 和具体 store 的继承顺序不会导致重复包装或漏包装。

### c. AtomicAction 边界

AtomicAction 边界负责“limiter 可以调用什么 action”。

backend-bound action helper 负责“action 构造后持有什么 backend”。

**（1）协议落点**

| 问题 | 处理方式 |
|------|----------|
| 在哪声明 | [1] 同步 `BaseAtomicAction` 与 `BackendBoundAtomicAction` 位于 `throttled/store/base.py`<br />[2] async 对应声明位于 `throttled/asyncio/store/base.py` |
| 上层如何取用 | [1] limiter 字典继续使用 `SyncAtomicActionP` / `AsyncAtomicActionP`<br />[2] 自定义 action 文档推荐继承 `BaseAtomicAction` |
| 如何收敛 | `_backend` 和构造器只放在 backend-bound helper 中，算法文件按具体 backend 继承 helper。 |

**（2）落点关系**

| 场景 | 处理方式 | 影响 |
|------|----------|------|
| Redis action | 继承 `BackendBoundAtomicAction[RedisStoreBackend]` 或等价 core helper。 | `register_script()` 仍拿到精确 Redis backend。 |
| Memory action | 共享 `_do(backend: MemoryStoreBackendP, ...)` 的纯计算逻辑。 | sync / async 只在锁和 `do()` 形态上分叉。 |
| 额外 action | 保持 `TYPE` / `STORE_TYPE` 身份筛选。 | 不要求第三方 action 暴露 backend 泛型。 |

**（3）实现约束**

- action 的 `TYPE` / `STORE_TYPE` 是注册身份，不是 backend 类型替代品。
- backend 类型只在 action 构造与执行内部使用。
- limiter 字典仍以 `SyncAtomicActionP` / `AsyncAtomicActionP` 保存能力。
- 不把 Redis action 的脚本类型抽象成 sync / async union。
- 不让 async Redis action 继承 sync Redis 执行 core。

### d. Throttled 泛型收敛

Throttled 层的核心问题不是泛型数量，而是一个共享 `__init__` 同时做了两类事：

```text
配置初始化：key / timeout / quota / cost
组合初始化：using 查出 limiter 类、store 保存到 _store、hooks 保存到 _hooks
```

配置初始化可以共享。

组合初始化必须在 sync / async 具体层完成。

**（1）构造参数策略**

当前公开构造允许位置参数。

公开参数顺序继续保持为 `key, timeout, using, quota, store, cost, hooks`。

收敛方案需要保留公开参数顺序，只在内部调用共享层时改成关键字传参。

| 参数 | 归属 | 处理方式 |
|------|------|----------|
| `key` | 共享层 | 保存为实例 key。 |
| `timeout` | 共享层 | 解析并校验等待策略。 |
| `quota` | 共享层 | 解析为 `Quota`。 |
| `cost` | 共享层 | 校验并保存默认 cost。 |
| `using` | sync / async | 通过对应 `RateLimiterRegistry.get()` 取 limiter 类。 |
| `store` | sync / async | 类型分别是同步 `BaseStore` 和异步 `BaseStore`。 |
| `hooks` | sync / async | 类型分别是 `Hook` 和 `AsyncHook`。 |

这个策略的结果是：公开构造签名不变，共享层不再接触 `store`、`using` 和 `hooks`。

**（2）优雅骨架**

```python
class BaseThrottledShared:
    __slots__ = ("key", "timeout", "_quota", "_cost")

    def __init__(
        self,
        *,
        key: KeyT | None = None,
        timeout: float | None = None,
        quota: Quota | str | None = None,
        cost: int = 1,
    ) -> None:
        self.key = key
        self.timeout = self._NON_BLOCKING if timeout is None else timeout
        self._validate_timeout(self.timeout)
        self._quota = self._parse_quota(quota)
        self._validate_cost(cost)
        self._cost = cost


class BaseThrottled(BaseThrottledShared):
    __slots__ = ("_store", "_limiter_cls", "_limiter", "_lock", "_hooks")

    _DEFAULT_GLOBAL_STORE: store.BaseStore = store.MemoryStore()

    def __init__(
        self,
        key: KeyT | None = None,
        timeout: float | None = None,
        using: RateLimiterTypeT | None = None,
        quota: Quota | str | None = None,
        store: store.BaseStore | None = None,
        cost: int = 1,
        hooks: Sequence[Hook] | None = None,
    ) -> None:
        super().__init__(key=key, timeout=timeout, quota=quota, cost=cost)
        self._store = self._resolve_store(store)
        self._limiter_cls = self._resolve_limiter_cls(using)
        self._limiter = None
        self._lock = self._get_lock()
        self._hooks = self._validate_hooks(hooks)

    def _make_limiter(self) -> BaseRateLimiter:
        return self._limiter_cls(self._quota, self._store)
```

async 侧复制公开参数顺序，只替换 `store`、`hooks`、`_limiter_cls` 和返回类型。

不要用 `*args` / `**kwargs` 转发这些参数。

显式签名能保留 IDE 补全、文档生成和 mypy 错误位置。

**（3）Limiter 类解析与构造**

`_make_limiter()` 的构造路径应直接走名义 Store 基类：

```text
sync:  store.BaseStore -> BaseRateLimiter.__init__ -> BaseRateLimiter
async: asyncio.store.BaseStore -> asyncio.BaseRateLimiter.__init__ -> asyncio.BaseRateLimiter
```

对应落点：

| 落点 | 处理方式 |
|------|----------|
| sync `BaseRateLimiter.__init__` | 接收 `store.BaseStore`。 |
| async `BaseRateLimiter.__init__` | 接收 `asyncio.store.BaseStore`。 |
| `_resolve_limiter_cls(using)` | 调用对应 `RateLimiterRegistry.get()`，把 `using` 转成 limiter 类。 |
| `_make_limiter()` | 只执行 `self._limiter_cls(self._quota, self._store)`。 |

现状说明：`RateLimiterRegistry.get()` 目前不能让 mypy 判断返回的是 sync 还是 async limiter 类。

若本轮不改它的签名，`_resolve_limiter_cls()` 可以保留一次 `cast`。

`_make_limiter()` 不再做类型转换。

**（4）迁移顺序**

1. 先把 sync / async `BaseRateLimiter` 的 store 参数切到对应 `BaseStore`。
2. 再拆 `BaseThrottledShared` 和 sync / async `BaseThrottled.__init__`。
3. 最后废弃 `StoreP`，并清理它在核心 TypeVar 约束中的使用。

**（5）实现边界**

- 公开构造签名保留当前位置参数顺序。
- 共享层只接收关键字参数，避免后续新增参数时错位。
- `_store`、`_limiter_cls`、`_limiter`、`_hooks`、`_make_limiter()` 和 `limiter` 不进入共享层。
- sync / async 可以重复少量组合代码，不重复 quota、timeout 和 cost 解析。
- `cast` 不进入用户 API、测试 fixture 或 `_make_limiter()`。

这个拆法的本质是：共享配置，不共享组合。

### e. 文档与测试迁移

文档和测试迁移负责证明 public API 的新边界可读、可用、可验证。

**（1）迁移对象**

| 对象 | 当前问题 | 目标处理 |
|------|----------|----------|
| 示例 `_get_store()` | 需要 `SyncStoreP` 或裸 `BaseStore` 报错。 | 改为 `BaseStore` 并返回具体 store 实例。 |
| `tests/conftest.py` | fixture 使用 `BaseStore[Any]` 或协议绕行。 | 改为 `BaseStore`、async `BaseStore` 或具体 store 类型。 |
| rate limiter 测试 | store fixture 把内部 backend 泛型带入算法测试。 | 测试 store stub 继承对应 `BaseStore`。 |
| Sphinx docs / docstring | `store` 参数说明与真实类型不一致。 | 说明普通用户和自定义 store 都使用对应 `BaseStore`。 |
| quickstart | `store=store` 容易误传模块对象。 | 改为 `store=_get_store()` 或 `store.RedisStore(...)`。 |

**（2）类型验收用例**

- 同步 `_get_store() -> BaseStore` 返回 `RedisStore`。
- 同步 `_get_store() -> BaseStore` 在 Redis / Memory 分支间切换。
- `Throttled(store=_get_store())` 通过 mypy。
- async `_get_store() -> asyncio.store.BaseStore` 返回 async Redis / Memory store。
- 继承 `BaseStore` 的测试桩可参与 limiter 测试。
- `SyncStoreP` / `AsyncStoreP` 不再是测试用例通过类型检查的必要条件。

**（3）回归约束**

- 不新增 `type: ignore`。
- 不把示例变成 `cast()` 驱动的通过。
- 不把测试 fixture 的类型退化成 `Any`。
- 不改变 Redis / Memory store 的构造参数。

## 0x04 验收与验证

重要测试点：

- `_get_store() -> BaseStore` 可返回 `MemoryStore` 或 `RedisStore`，并可传给 `Throttled(store=...)`。
- async `_get_store() -> asyncio.store.BaseStore` 可返回 async `MemoryStore` 或 async `RedisStore`。
- `Throttled` 与 async `Throttled` 的现有位置参数顺序保持可用。
- sync / async hooks 仍按各自类型校验，错误 hook 类型仍报错。
- sync / async `limiter` 懒加载后拿到的 store 是传入的名义 `BaseStore` 实例。
- `StoreP` 不再作为核心 TypeVar 约束，也不出现在公开构造签名中。
- 不新增 `BaseStore[Any]`、`type: ignore` 或面向用户 API 的 `cast()`。

## 0x05 实施进展

| 时间 | 对应设计片段 | 结论调整概要 | 改动 / 验证 |
|------|--------------|--------------|-------------|
| `2026-05-06 02:00` | `0x02-b`、`0x02-e`、`0x03-d`、`0x04` | [1] 删除独立 Store 协议删除章节，`StoreP` 废弃口径合并到边界不变量。<br />[2] Throttled 共享边界改为标准 Mermaid 类图，只声明继承关系和成员归属。<br />[3] `0x03-d` 改为“共享配置，不共享组合”，补充位置参数兼容骨架。<br />[4] 验收改为只保留本需求关键测试点。 | [1] 已用 `classDiagram` 表达 `BaseThrottledShared -> sync / async` 的类关系。<br />[2] 已删除 Store、Limiter 和 Hook 的第三层依赖节点。<br />[3] 已基于当前 `BaseThrottledMixin.__init__` 位置参数顺序重写构造方案。<br />[4] 已回收难读术语，改成可对应源码动作的表达。 |
| `2026-05-06 01:00` | `0x02`、`0x03` | [1] 架构设计改为只承载分层、类型语义与不变量。<br />[2] 开发方案改为按责任边界组织，补齐协议落点、收敛入口、迁移规则和禁止形态。 | [1] 已将 `BaseStore` / `BaseAtomicAction` 的最小结构下沉到开发方案。<br />[2] 已把 Store、backend-bound helper、AtomicAction、Throttled 与文档测试迁移拆成独立落点。 |
| `2026-05-06 00:00` | `0x01` 至 `0x04` | [1] 已确认 HTTPX 使用非泛型 public base transport 承载用户侧能力边界。<br />[2] 已确认 throttled-py 的 `BaseStore[_BackendT]` 将 backend 配对泄漏到用户侧。<br />[3] 推荐拆分 `BaseStore` 与 `BackendBoundStore[_BackendT]`，后续再收敛 `BaseThrottledMixin`。 | [1] 已核对 HTTPX `BaseTransport`、`HTTPTransport`、`MockTransport`、`WSGITransport`、`ASGITransport` 与 `Client` 源码。<br />[2] 已核对 throttled-py store、types、rate limiter 与 throttled 主路径。<br />[3] 已用 `mypy --strict -c` 复现 `BaseStore` 裸用失败与 `SyncStoreP` 通过。 |

## 0x06 参考

- [HTTPX Transports 文档](https://www.python-httpx.org/advanced/transports/)
- [HTTPX `BaseTransport` 源码](https://github.com/encode/httpx/blob/master/httpx/_transports/base.py)
- [HTTPX `HTTPTransport` 源码](https://github.com/encode/httpx/blob/master/httpx/_transports/default.py)
- [HTTPX `MockTransport` 源码](https://github.com/encode/httpx/blob/master/httpx/_transports/mock.py)
- [HTTPX `WSGITransport` 源码](https://github.com/encode/httpx/blob/master/httpx/_transports/wsgi.py)
- [HTTPX `ASGITransport` 源码](https://github.com/encode/httpx/blob/master/httpx/_transports/asgi.py)
- [HTTPX `Client` 源码](https://github.com/encode/httpx/blob/master/httpx/_client.py)
- [mypy strict 模式合规改造方案](../2026-04-06-mypy-strict-compliance/PLAN.md)
- [优化存储不可用时的异常处理方案](../2026-05-03-store-unavailable-error-handling/PLAN.md)

## 0x07 版本锚点

- 建议分支：`refactor/260506_store_typing_boundary`
- PR：待创建。
