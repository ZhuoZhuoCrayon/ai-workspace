---
title: mypy strict 模式合规改造方案
tags: [throttled-py, typing, mypy, strict]
issue: ./README.md
description: 四阶段修复 248 个 mypy --strict 错误的实施方案
created: 2026-04-06
updated: 2026-04-07
---

# mypy strict 模式合规改造 —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 调研

### a. 错误热点分析

按文件统计（截取 top 7）：

- `throttled/utils.py`：~35 errors — 缺失注解（Timer、Benchmark、import_string）
- `throttled/store/redis_pool.py`：~15 errors — redis 类型别名、参数 Optional、工厂方法注解
- `throttled/store/redis.py`：~15 errors — `_set_*` 返回注解、`_parse` 内变量重定义
- `throttled/asyncio/rate_limiter/*.py`：~80 errors — async 联合类型泄漏
- `throttled/asyncio/store/memory.py`：~10 errors — `_get_lock` / lock 联合类型
- `throttled/rate_limiter/base.py`：~6 errors — Quota dataclass、Registry/Meta 注解缺失
- `throttled/exceptions.py`：1 error — `message` 变量重定义

### b. 核心矛盾

async 侧错误占总量 ~60%。根因与 `BaseThrottledMixin` 相同 —— sync/async 共用基类导致属性类型为联合类型：

```text
BaseRateLimiterMixin
├── _store: StoreP (= _SyncStoreP | _AsyncStoreP)
├── _atomic_actions: dict[str, AtomicActionP (= Sync | Async)]
│
├── sync BaseRateLimiter ── .do() → tuple          ✓ 直接用
└── async BaseRateLimiter ── await .do() → ???      💥 union 不可 await
```

## 0x02 方案设计

### a. async 侧类型窄化（属性重注解与集中 accessor）

`BaseRateLimiterMixin` 存在 CoreMixin 菱形继承 + `RateLimiterMeta` 元类，Generic 化成本高且引入 MRO 风险。

**方案**：分两层窄化。

**第一层 —— `_store` 属性重注解**：`_AsyncStoreP` 是 `StoreP`（`_SyncStoreP | _AsyncStoreP`）的子类型，不涉及容器 invariance，mypy 允许子类收窄简单属性类型。

**第二层 —— `_atomic_actions` 集中 accessor**：`dict` 是 invariant 容器，`dict[K, _AsyncAtomicActionP]` 不是 `dict[K, AtomicActionP]` 的子类型，直接属性窄化会报 `Incompatible types in assignment`。改用集中 accessor 方法，cast 仅出现一处。

涉及文件：`throttled/asyncio/rate_limiter/base.py`

```python
class BaseRateLimiter(rate_limiter.BaseRateLimiterMixin, metaclass=RateLimiterMeta):
    _store: _AsyncStoreP  # 属性窄化 — OK

    def _get_atomic_action(self, action_type: AtomicActionTypeT) -> _AsyncAtomicActionP:
        return cast("_AsyncAtomicActionP", self._atomic_actions[action_type])
```

sync 侧同理：在 `throttled/rate_limiter/base.py` 的 `BaseRateLimiter` 中加 `_get_atomic_action() -> _SyncAtomicActionP`。

`_limit`/`_peek` 方法统一通过 `self._get_atomic_action(...)` 获取 action，不再逐个 cast。

同理，`throttled/asyncio/store/memory.py` 中窄化 lock 类型：

```python
class MemoryStoreBackend(store.MemoryStoreBackend):
    lock: _AsyncLockP

    @classmethod
    def _get_lock(cls) -> _AsyncLockP:
        return asyncio.Lock()
```

**类型解析依赖**：`BaseRateLimiterMixin._register_atomic_actions` 中 `self._store.make_atomic()` 返回 `AtomicActionP`（union），赋给 `self._atomic_actions`。

mypy 按**方法定义所在类**解析属性类型，mixin 内看到的仍是 union 类型，不会与 async 子类的窄化声明冲突。

**已知折中**：

- `make_atomic` 返回类型暂不拆分为 sync/async 两个 Protocol。`type[Protocol]` 在 mypy 中不可直接调用，需 `cast("Any", action_cls)(...)` 绕过。外层 cast 用变量注解替代，减少嵌套：

```python
def make_atomic(self, action_cls: type[AtomicActionP]) -> AtomicActionP:
    instance: AtomicActionP = cast("Any", action_cls)(backend=self._backend)
    return instance
```

- `_get_lock` 返回 `asyncio.Lock()` 在 PyCharm 中会产生 `Expected type '_AsyncLockP', got 'Lock'` 警告，属 PyCharm 类型检查器 false positive。mypy 通过即可，不阻塞。

### b. AtomicAction Protocol 修复

两个问题：

1. `do()` 返回 `tuple[int, ...]`，但具体实现返回 `tuple[int, int, float, float]`（GCRA）或 `tuple[int, int]`（TokenBucket）
2. `__init__(backend: StoreBackendP)` 导致 `type[ConcreteClass]`（参数更窄）无法赋给 `type[Protocol]`

**修复**：

- `do()` 返回类型 → `tuple[int | float, ...]`，覆盖所有具体实现（固定长度元组是可变长度同类元组的子类型）
- 从 Protocol 移除 `__init__`，构造器不属于实例结构契约（PEP 544）
- 同步修改 `BaseAtomicAction`（ABC）的 `do()` 返回类型

**调用处处理策略**：

`do()` 返回 `tuple[int | float, ...]` 后，解包变量推断为 `int | float`，传给 `state_values: Tuple[int, int, float, float]` 等精确类型时会报错。

各算法的 `_limit`/`_peek` 方法明确知道返回形状，在调用处用 `cast` 恢复精确类型（零运行时开销）。

涉及文件：`throttled/types.py`、`throttled/store/base.py`、`throttled/asyncio/store/base.py`

### c. list → Sequence（协变容器）

`_DEFAULT_ATOMIC_ACTION_CLASSES: list[type[AtomicActionP]]` 中 `list` 是 invariant，子类赋值报错。

**修复**：改用 `Sequence`（covariant），涉及所有 CoreMixin 和 concrete rate limiter 类。

### d. Quota dataclass

`period_sec: int = None` 声明 `int` 但默认 `None`，`__post_init__` 中才赋值。

**修复**：使用 `field(init=False)` 声明计算字段，`__post_init__` 中赋值并加类型注解。

### e. 工具函数与连接池注解补全

纯注解补全工作，无架构变更，按 mypy 报错逐项修复。

### f. 变量重定义（redef）统一处理

sync/async 两侧 rate limiter 中存在分支内重复类型注解（如 `limited: int = 1` / `limited: int = 0`），mypy --strict 报 `Name already defined`。

**修复**：在分支前统一声明变量类型，分支内仅赋值不重复注解：

```python
limited: int
retry_after: float
reset_after: float
if condition:
    limited = 1
    ...
else:
    limited = 0
    ...
```

涉及文件：`throttled/rate_limiter/gcra.py`、`throttled/rate_limiter/token_bucket.py` 及对应 async 侧。

## 0x03 实施步骤

### a. 基础注解补全

| 文件 | 改动 |
|------|------|
| `throttled/utils.py` | [1] Timer、Benchmark 全部方法加注解<br />[2] `_callback` 改 Optional<br />[3] `_start` 消除 redef<br />[4] `import_string` 加返回类型 |
| `throttled/exceptions.py` | `message` 变量消除 `no-redef`（首次声明注解，后续不重复） |
| `throttled/rate_limiter/base.py` | [1] Quota 计算字段用 `field(init=False)`<br />[2] `register`、`__new__` 加注解 |
| `throttled/rate_limiter/gcra.py` | `_do` 等方法内分支变量 redef 修复（提前声明类型） |
| `throttled/rate_limiter/token_bucket.py` | 同上 redef 修复 |
| `throttled/store/redis.py` | [1] `_set_*` 加 `-> None`<br />[2] `_parse` 内 `options`/`parsed` 消除 redef *[a]* |
| `throttled/store/redis_pool.py` | [1] `DefaultParser` 加 TypeAlias<br />[2] `url: str = None` → `str \| None = None` *[b]*<br />[3] 工厂方法加注解<br />[4] redis union 处理 |

- *[a]* 使用不同变量名避免同名覆盖。
- *[b]* 含 `make_connection_params`、`connect` 两处。

### b. Protocol 与类型体系修正

| 文件 | 改动 |
|------|------|
| `throttled/types.py` | [1] `do()` → `tuple[int \| float, ...]`<br />[2] 移除 AtomicAction Protocol 的 `__init__` |
| `throttled/store/base.py` | [1] `BaseAtomicAction.do()` → `tuple[int \| float, ...]`<br />[2] `get_client()` 加返回类型 |
| `throttled/asyncio/store/base.py` | async `BaseAtomicAction.do()` 同步修改 |
| 所有 rate limiter CoreMixin + concrete | [1] `_DEFAULT_ATOMIC_ACTION_CLASSES` 从 `list` → `Sequence`<br />[2] `do()` 调用处按算法精确 cast 返回类型 |

### c. sync 和 async 侧联合类型窄化

| 文件 | 改动 |
|------|------|
| `throttled/asyncio/rate_limiter/base.py` | [1] `_store: _AsyncStoreP`（属性窄化）<br />[2] 新增 `_get_atomic_action()` 集中 accessor *[c]* |
| `throttled/rate_limiter/base.py` | 新增 sync 侧 `_get_atomic_action() -> _SyncAtomicActionP` |
| `throttled/asyncio/store/memory.py` | [1] `_get_lock` → `@classmethod`<br />[2] `lock: _AsyncLockP` |
| async rate limiter concrete 类（5 个） | [1] `_limit`/`_peek` 改用 `self._get_atomic_action(...)`<br />[2] `no-any-return` 修复（Redis script 返回值 cast）<br />[3] `int \| float → int` 赋值修复<br />[4] 分支变量 redef 修复 |
| sync rate limiter concrete 类（5 个） | 同上，改用 `self._get_atomic_action(...)` |
| `throttled/asyncio/rate_limiter/__init__.py` | 修复 `GCRARateLimiterCoreMixin` 导出 |

- *[c]* `_atomic_actions` 因 `dict` invariance 不可直接属性窄化，改用集中 accessor 方法 cast 一次。

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
| 2026-04-07 | 按 PR #145 review 对齐方案，回归“属性窄化 + 精确 cast + 行为不变”原则；收敛过度分散 cast 并恢复关键初始化链路；完成 commitlint 合规提交。 | [1] async/sync `BaseRateLimiter` 增加 `_store` 窄化入口与 `_get_atomic_action` 统一窄化调用<br />[2] `types.py` 移除 AtomicAction Protocol `__init__`，`make_atomic` 调整为兼容构造调用<br />[3] Redis `hset` 恢复直接透传调用，避免行为漂移<br />[4] 5 个 sync + 5 个 async rate limiter 改为精确元组 cast，去除 `_raw + int/float` 双转换<br />[5] CoreMixin 恢复 `super().__init__(backend)` 并移除无用 `backend` property<br />[6] 校验通过：`ruff`、`mypy --strict`、`pytest`、`pre-commit --files` 全绿<br />[7] PR：[#145](https://github.com/ZhuoZhuoCrayon/throttled-py/pull/145)，提交：`20eb1ee`（`refactor: align codebase with mypy strict compliance`）<br />[8] 严格按 `0x02.a/0x03.c` 落地 async memory lock 窄化：`lock: _AsyncLockP` + `_get_lock() -> _AsyncLockP` + `async with self._backend.lock`，提交：`5639a49`<br />[9] `make_atomic` 进一步对齐“集中 accessor”章节建议：改为变量注解单层 cast（去掉嵌套 cast），提交：`ad34a00` |

## 0x06 参考

- [排障经验：同步异步共用 Mixin 的泛型类型窄化](../../troubleshooting/generic-mixin-type-narrowing.md)
- [mypy — Protocols and structural subtyping](https://mypy.readthedocs.io/en/stable/protocols.html)
- [PEP 544 — Protocols](https://peps.python.org/pep-0544/)

## 0x07 版本锚点

- 分支：`fix/260406_mypy_strict`
- PR：[#145](https://github.com/ZhuoZhuoCrayon/throttled-py/pull/145)
- 提交：`ad34a00`
