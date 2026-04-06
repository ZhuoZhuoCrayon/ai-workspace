---
title: throttled-py 可读容量配置 DSL 实施方案
tags: [throttled-py, quota, dsl, planning, research]
issue: knowledge/throttled-py/issues/2026-04-04-quota-dsl-research-and-requirement/README.md
description: 基于主流库语法调研，定义 throttled-py quota 字符串语法的实现方案与落地路径
created: 2026-04-04
updated: 2026-04-06
---

# throttled-py 可读容量配置 DSL —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 调研

### a. 主流库调研结论（2026-04-04 快照）

| 库 | 主要语法模式 | 单规则语法 | 多规则语法（同一 cell 换行） | 适配提示 |
|------|------|------|------|------|
| `limits` | 字符串：`n/unit`、`n per unit` | `parse("1/minute")` | `parse_many("1/second; 5/minute")`<br />分隔符：逗号 `,`、分号 `;`、竖线（pipe） | 可直接作为 `quota.parse` 设计参考 |
| `Flask-Limiter` | 字符串：`n per unit` | `@limiter.limit("1 per day")` | `default_limits=["2 per minute", "1 per second"]` | 说明“多规则列表”体验在框架侧很常见 |
| `slowapi` | 字符串：`n/unit` | `@limiter.limit("5/minute")` | `@limiter.limit("5/minute")`<br />`@limiter.limit("100/hour")` | 与 `limits` 语法一致性高 |
| `django-ratelimit` | 短字符串：`n/u`（`s/m/h/d`） | `rate='5/m'` | `@ratelimit(..., rate='10/s')`<br />`@ratelimit(..., rate='100/m')` | 短语法对配置项长度友好 |
| `fastapi-limiter` | 对象：`Rate + Duration` | `Limiter(Rate(2, Duration.SECOND * 5))` | `Depends(RateLimiter(...Rate(1, Duration.SECOND * 5)))`<br />`Depends(RateLimiter(...Rate(2, Duration.SECOND * 15)))` | 非 DSL，但多规则组合方式可借鉴 |
| `pyrate-limiter` | 对象：`Rate + Duration` | `Rate(5, Duration.SECOND * 2)` | `rates=[Rate(3, 1000), Rate(4, 1500)]` | 内核表达力强，适合作为内部模型 |
| `aiolimiter` | 数值参数：`(max_rate, time_period)` | `AsyncLimiter(100, 30)` | 多个 limiter 实例并用 | 适合极简场景，不适合作为 DSL 参考主轴 |

### b. 调研结论

- 生态主流形态是“请求数 + 时间单位”的短字符串表达。
- `n/unit` 与 `n per unit` 是最值得优先兼容的两种写法。
- 多规则串联在 `limits` 中已有成熟实践，可作为解析层能力参考。

## 0x02 方案设计

### a. 决策共识

- 语法兼容：向前兼容 `limits` 的 `n/unit` 与 `n per unit`。
- 能力边界：`parse` 支持多规则；`Throttled(quota=...)` 暂不支持多规则执行。
- 版本定位：优先稳定单规则主路径，后续再开放多规则执行。

### b. 单位模型与归一化

| 标准单位 | 兼容写法 | 时长 |
|------|------|------|
| `second` | `s`, `sec`, `secs`, `second`, `seconds` | 1s |
| `minute` | `m`, `min`, `mins`, `minute`, `minutes` | 60s |
| `hour` | `h`, `hr`, `hrs`, `hour`, `hours` | 3600s |
| `day` | `d`, `day`, `days` | 86400s |
| `week` | `w`, `wk`, `wks`, `week`, `weeks` | 604800s |

- 不支持 `month`、`year` 等非固定时长单位。
- 解析后统一映射到内部标准单位，避免执行层语义分叉。

### c. burst 语义与默认规则

- `burst` 关键字语法：`<rate> burst <n>`。
- 默认规则：若未显式声明 `burst`，默认取同一规则中的 `n`。
  - 示例：`1/s` 等价于 `1/s burst 1`。
- 生效算法：`TOKEN_BUCKET`、`LEAKING_BUCKET`、`GCRA`。

### d. 多规则与分隔策略

- 推荐分隔符：`;`（规则间分隔）。
- 兼容分隔符：`,` 与竖线（pipe）。
- 多规则解析能力仅在 `parse` 层开放。
- 对 `Throttled(quota="...")` 传入多规则时返回明确错误，不做隐式降级。

### e. 错误与兼容策略

- 错误信息包含：非法片段、期望格式、可选示例。
- 对现有对象式配置（`rate_limiter.per_*` / `Quota`）保持兼容，不做破坏性变更。
- 同一输入在 sync / async 下保持一致解析与一致判定。

### f. 文档与示例落地规范

- 文档主路径采用字符串配置表达，不引入用户难理解术语。
- Quick Setup 采用 pattern-first 展示，明确 4 种模式：
  - `n / unit`
  - `n / unit burst <burst>`
  - `n per unit`
  - `n per unit burst <burst>`
- 文档示例优先 `literalinclude` 引用 `examples`，避免重复维护。

## 0x03 实施步骤

1. 定义字符串语法规范，锁定单位映射、分隔符和 `burst` 默认规则。
2. 实现 `quota.parse()`，支持单规则与多规则解析。
3. 实现 `Throttled(quota="...")` 单规则适配，并对多规则输入抛出明确错误。
4. 增加解析成功与失败测试，覆盖边界值与兼容场景。
5. 增加单位归一化测试与 `burst` 默认值测试。
6. 更新 `README` / docs / examples，补充迁移示例与反例说明。

## 0x04 验收与验证

- 目标用例：`uv run pytest -n auto tests/rate_limiter/test_quota_parser.py tests/test_throttled.py tests/asyncio/test_throttled.py`。
- 全量回归（2026-04-06）：`uv run pytest -n auto tests/`，结果 `679 passed, 51 skipped`。
- 门禁：`uv run prek run --files ...`（`ruff`、`ruff-format`、`mypy-strict`）。
- 文档：`cd docs && uv run make html` 构建通过。

## 0x05 实施进展（表格）

| 时间 | 结论调整概要 | 改动 |
|------|------|------|
| 2026-04-05 | [1] 解析能力归类到 `rate_limiter` 领域，不新增顶层 `quota` 兼容层。<br />[2] 语法兼容 `n/unit`、`n per unit`。<br />[3] `parse` 支持多规则，`Throttled` 暂不支持多规则执行。 | [1] 新增 `throttled/rate_limiter/quota_parser.py`。<br />[2] `Throttled` 接入字符串 `quota`。<br />[3] 新增 `tests/rate_limiter/test_quota_parser.py`，并补充 sync/async 相关用例。 |
| 2026-04-05 | [1] 统一 `burst` 语法为关键字空格 `<rate> burst <n>`。<br />[2] 保留逗号分隔符兼容（与 `limits` 一致）。 | [1] 解析规则调整并补充测试。<br />[2] 文档中同步语法决策说明。 |
| 2026-04-06 | [1] 文档结构采用 pattern-first。<br />[2] 字符串模式下 `burst` 默认取同一规则中的 `n`（如 `1/s == 1/s burst 1`）。<br />[3] 结论性规则并入方案设计主干，避免“追加修正”割裂阅读。 | [1] `docs/source/quickstart/quota-configuration.rst` 重构并修复 `Malformed table`。<br />[2] `README.md` / `README_ZH.md` quota 区块统一为字符串主路径，并补充默认 `burst` 规则。<br />[3] `examples/quickstart`（含 async）统一 quota 字符串写法。 |
| 2026-04-06 | [1] PR 内过程性结论统一收敛到本 `PLAN.md`。<br />[2] PR review threads 全部标记 resolved（含已采纳与有结论不改动项）。<br />[3] 针对 DSL 变更完成全量回归复验。 | [1] 精简 PR conversation / inline 过程记录并改为指向 `PLAN`。<br />[2] resolved review threads：`quota_parser` 分隔符讨论、`BaseThrottledMixin` 类型收敛讨论、文档 discoverability 讨论。<br />[3] 复验：`679 passed, 51 skipped`。 |

## 0x06 参考

- [limits Quickstart](https://limits.readthedocs.io/en/stable/quickstart.html)
- [limits API](https://limits.readthedocs.io/en/stable/api.html)
- [<源码> limits limits/util.py](https://github.com/alisaifee/limits/blob/master/limits/util.py)
- [Flask-Limiter](https://github.com/alisaifee/flask-limiter/blob/master/README.rst)
- [slowapi Docs](https://slowapi.readthedocs.io/en/latest/)
- [django-ratelimit Usage](https://django-ratelimit.readthedocs.io/en/stable/usage.html)
- [fastapi-limiter](https://github.com/long2ice/fastapi-limiter/blob/main/README.md)
- [PyrateLimiter](https://github.com/vutran1710/PyrateLimiter/blob/master/README.md)
- [aiolimiter](https://github.com/mjpieters/aiolimiter/blob/main/README.md)

## 0x07 版本锚点

- 分支：`feat/260405_quota_parser_dsl`
- PR：[#141](https://github.com/ZhuoZhuoCrayon/throttled-py/pull/141)
