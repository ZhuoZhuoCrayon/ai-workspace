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
| `limits` | 字符串：`n/unit`、`n per unit` | `parse("1/minute")` | `parse_many("1/second; 5/minute")`<br />分隔符：`,` `;` `|` | 可直接作为 `quota.parse` 设计参考 |
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

### a. 能力范围

- 新增 `quota.parse()`，用于解析 quota 字符串。
- 新增 `Throttled(quota="...")` 字符串入口。
- 保持现有 `Quota`、`Rate`、`per_sec` 等 API 完整兼容。

### b. DSL 语法约定（v1）

- 基础速率：支持 `100/s`、`100/m`、`100/h`、`100/d`、`100/w`。
- 自然语言：支持 `100 per second`、`100 per minute` 等形式。
- 爆发配置：支持 `burst=200`。
- 多规则串联：支持分隔符拼接多条规则，优先约定 `;`。

### c. 错误与兼容策略

- 错误信息包含非法片段、期望格式、可选示例。
- 对现有对象式配置无破坏性变更。
- 对 sync / async 维持一致语义与行为。

## 0x03 实施步骤

1. 定义 DSL 语法规范文档，锁定单位映射、分隔符和 burst 规则。
2. 实现 `quota.parse()` 与 `Throttled` 字符串入口适配。
3. 增加解析成功与失败测试，覆盖边界值与兼容场景。
4. 增加多规则 DSL 与对象规则一致性测试。
5. 更新 README 与 docs，补充迁移示例与反例说明。
6. 以 M1 验收标准完成评审与合并。

## 0x04 参考

### a. 语法参考

- `limits` Quickstart: <https://limits.readthedocs.io/en/stable/quickstart.html>
- `limits` API: <https://limits.readthedocs.io/en/stable/api.html>
- `limits` source: <https://github.com/alisaifee/limits/blob/master/limits/util.py>
- `Flask-Limiter` README: <https://github.com/alisaifee/flask-limiter/blob/master/README.rst>
- `slowapi` docs: <https://slowapi.readthedocs.io/en/latest/>
- `django-ratelimit` Usage: <https://django-ratelimit.readthedocs.io/en/stable/usage.html>

### b. 生态参考

- `fastapi-limiter` README: <https://github.com/long2ice/fastapi-limiter/blob/main/README.md>
- `PyrateLimiter` README: <https://github.com/vutran1710/PyrateLimiter/blob/master/README.md>
- `aiolimiter` README: <https://github.com/mjpieters/aiolimiter/blob/main/README.md>

---
*制定日期：2026-04-04*
