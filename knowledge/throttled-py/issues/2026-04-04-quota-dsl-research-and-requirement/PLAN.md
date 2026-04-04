---
title: throttled-py 可读容量配置 DSL 实施方案
tags: [throttled-py, quota, dsl, planning, research]
issue: knowledge/throttled-py/issues/2026-04-04-quota-dsl-research-and-requirement/README.md
description: 基于主流库语法调研，定义 throttled-py quota DSL 的实现方案与步骤
created: 2026-04-04
updated: 2026-04-04
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

### b. 结论

- 生态主流 DSL 形态是“请求数 + 时间单位”的短字符串表达。
- `n/unit` 与 `n per unit` 是最值得优先兼容的两种写法。
- 多规则串联在 `limits` 中已有成熟实践，可作为 `throttled-py` 规则字符串入口参考。

## 0x02 方案设计

### a. 决策共识（2026-04-04）

- 语法兼容：按 `limits` 语法兼容 `n/unit`、`n per unit`。
- 单位兼容：`unit` 同时支持简写与全写。
  - 简写：`s`、`m`、`h`、`d`、`w`。
  - 全写：`second`、`minute`、`hour`、`day`、`week`，含复数形式。
- `burst` 规则：默认 `burst = n`，同时支持显式声明覆盖。
  - 示例：`1/s` 默认 `burst=1`。
  - 示例：`1/s; burst=5` 显式覆盖默认值。
- 能力边界：`parse` 支持多规则，`Throttled` 暂不支持多规则。
- 版本定位：向前兼容 `limits`，同时提供扩展与增强。

### b. 语法与行为约束（v1）

- 推荐分隔符：`；` 对应 ASCII 形式 `;`。
- 兼容分隔符：兼容 `,` 与竖线（pipe）。
- 归一化：解析后统一映射到内部标准单位模型，避免简写与全写在执行层分叉。
- 稳定性：同一输入在 sync / async 下保持一致解析与一致判定。

### c. 错误与兼容策略

- 错误信息包含非法片段、期望格式、可选示例。
- `Throttled(quota="...")` 传入多规则时返回明确错误，不做隐式降级。
- 对现有对象式配置无破坏性变更。

## 0x03 实施步骤

1. 定义 DSL 语法规范文档，锁定单位映射、分隔符和 `burst` 默认规则。
2. 实现 `quota.parse()`，支持单规则与多规则解析。
3. 实现 `Throttled(quota="...")` 单规则适配，并对多规则输入抛出明确错误。
4. 增加解析成功与失败测试，覆盖边界值与兼容场景。
5. 增加单位简写/全写归一化测试与 `burst` 默认值测试。
6. 更新 README 与 docs，补充迁移示例与反例说明。

## 0x04 参考

- [limits Quickstart](https://limits.readthedocs.io/en/stable/quickstart.html)
- [limits API](https://limits.readthedocs.io/en/stable/api.html)
- [<源码> limits limits/util.py](https://github.com/alisaifee/limits/blob/master/limits/util.py)
- [Flask-Limiter README](https://github.com/alisaifee/flask-limiter/blob/master/README.rst)
- [slowapi Docs](https://slowapi.readthedocs.io/en/latest/)
- [django-ratelimit Usage](https://django-ratelimit.readthedocs.io/en/stable/usage.html)
- [fastapi-limiter](https://github.com/long2ice/fastapi-limiter/blob/main/README.md)
- [PyrateLimiter README](https://github.com/vutran1710/PyrateLimiter/blob/master/README.md)
- [aiolimiter README](https://github.com/mjpieters/aiolimiter/blob/main/README.md)
