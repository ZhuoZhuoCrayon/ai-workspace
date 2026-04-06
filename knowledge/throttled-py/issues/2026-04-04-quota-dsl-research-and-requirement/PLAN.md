---
title: throttled-py 可读容量配置 DSL 实施方案
tags: [throttled-py, quota, dsl, planning, research]
issue: knowledge/throttled-py/issues/2026-04-04-quota-dsl-research-and-requirement/README.md
description: 基于主流库语法调研，定义 throttled-py quota DSL 的实现方案与步骤
created: 2026-04-04
updated: 2026-04-06
---

# throttled-py 可读容量配置 DSL —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 调研

### a. 主流库调研结论（2026-04-04 快照）

| 库                  | 主要语法模式                         | 单规则语法                                   | 多规则语法（同一 cell 换行）                                                                                                     | 适配提示                     |
|--------------------|--------------------------------|-----------------------------------------|-----------------------------------------------------------------------------------------------------------------------|--------------------------|
| `limits`           | 字符串：`n/unit`、`n per unit`      | `parse("1/minute")`                     | `parse_many("1/second; 5/minute")`<br />分隔符：逗号 `,`、分号 `;`、竖线（pipe）                                                    | 可直接作为 `quota.parse` 设计参考 |
| `Flask-Limiter`    | 字符串：`n per unit`               | `@limiter.limit("1 per day")`           | `default_limits=["2 per minute", "1 per second"]`                                                                     | 说明“多规则列表”体验在框架侧很常见       |
| `slowapi`          | 字符串：`n/unit`                   | `@limiter.limit("5/minute")`            | `@limiter.limit("5/minute")`<br />`@limiter.limit("100/hour")`                                                        | 与 `limits` 语法一致性高        |
| `django-ratelimit` | 短字符串：`n/u`（`s/m/h/d`）          | `rate='5/m'`                            | `@ratelimit(..., rate='10/s')`<br />`@ratelimit(..., rate='100/m')`                                                   | 短语法对配置项长度友好              |
| `fastapi-limiter`  | 对象：`Rate + Duration`           | `Limiter(Rate(2, Duration.SECOND * 5))` | `Depends(RateLimiter(...Rate(1, Duration.SECOND * 5)))`<br />`Depends(RateLimiter(...Rate(2, Duration.SECOND * 15)))` | 非 DSL，但多规则组合方式可借鉴        |
| `pyrate-limiter`   | 对象：`Rate + Duration`           | `Rate(5, Duration.SECOND * 2)`          | `rates=[Rate(3, 1000), Rate(4, 1500)]`                                                                                | 内核表达力强，适合作为内部模型          |
| `aiolimiter`       | 数值参数：`(max_rate, time_period)` | `AsyncLimiter(100, 30)`                 | 多个 limiter 实例并用                                                                                                       | 适合极简场景，不适合作为 DSL 参考主轴    |

### b. 结论

- 生态主流 DSL 形态是“请求数 + 时间单位”的短字符串表达。
- `n/unit` 与 `n per unit` 是最值得优先兼容的两种写法。
- 多规则串联在 `limits` 中已有成熟实践，可作为 `throttled-py` 规则字符串入口参考。

## 0x02 方案设计

### a. 决策共识（2026-04-04）

- 语法兼容：按 `limits` 语法兼容 `n/unit`、`n per unit`。
- 单位兼容：`unit` 同时支持简写与全写，解析后归一化到标准单位。

| 标准单位     | 兼容写法                                    | 时长      |
|----------|-----------------------------------------|---------|
| `second` | `s`, `sec`, `secs`, `second`, `seconds` | 1s      |
| `minute` | `m`, `min`, `mins`, `minute`, `minutes` | 60s     |
| `hour`   | `h`, `hr`, `hrs`, `hour`, `hours`       | 3600s   |
| `day`    | `d`, `day`, `days`                      | 86400s  |
| `week`   | `w`, `wk`, `wks`, `week`, `weeks`       | 604800s |

> 不支持 `month`、`year` 等非固定时长单位。
- `burst` 规则：默认 `burst = n`，同时支持显式声明覆盖。
  - 示例：`1/s` 默认 `burst=1`。
  - 示例：`1/s burst 5` 显式覆盖默认值。
  - **语法决策（2026-04-05）**：采用关键字空格方案 `<rate> burst <n>`，不使用 `burst=<n>` 分号分隔。
    - 理由：`;` 同时用于规则分隔和 burst 修饰导致语义歧义；关键字空格在 `n/unit` 和 `n per unit` 两种记法下均自然通顺。
    - 调研依据：nginx（`burst=N` 独立参数）、redis-cell（`max_burst` 位置参数）、Traefik（`burst` 平级字段）等主流系统均将 burst 与 rate 分离表达，无一使用 `;` 复用。
- 能力边界：`parse` 支持多规则，`Throttled` 暂不支持多规则。
- 版本定位：向前兼容 `limits`，同时提供扩展与增强。

### b. 语法与行为约束（v1）

- 推荐分隔符：`;`（规则间分隔）。
- 兼容分隔符：兼容 `,` 与竖线（pipe）。
- burst 修饰：`<rate> burst <n>`（关键字空格），不复用规则分隔符。
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
- [Flask-Limiter](https://github.com/alisaifee/flask-limiter/blob/master/README.rst)
- [slowapi Docs](https://slowapi.readthedocs.io/en/latest/)
- [django-ratelimit Usage](https://django-ratelimit.readthedocs.io/en/stable/usage.html)
- [fastapi-limiter](https://github.com/long2ice/fastapi-limiter/blob/main/README.md)
- [PyrateLimiter](https://github.com/vutran1710/PyrateLimiter/blob/master/README.md)
- [aiolimiter](https://github.com/mjpieters/aiolimiter/blob/main/README.md)

## 0x05 实施进展（2026-04-05）

### a. 变更摘要

- 新增解析模块：`throttled/rate_limiter/quota_parser.py`。
- `Throttled` 支持字符串 quota，并接入 `quota_parser`。
- `parse` 支持多规则；`Throttled(quota=...)` 暂不支持多规则执行并抛出明确错误。
- 新增 `tests/test_quota.py`，并补充 `tests/asyncio/test_throttled.py` 相关用例。

### b. 关键结论

- 解析能力归类到 `rate_limiter` 领域，不新增顶层 `quota` 兼容层。
- 语法兼容 `limits` 主流写法（`n/unit`、`n per unit`），并支持 `burst` 默认值与显式覆盖。
- 先稳定单规则主路径，后续再开放多规则执行。

### c. 验证

- `uv run pytest -q tests/test_quota.py tests/test_throttled.py tests/asyncio/test_throttled.py`：`46 passed`。
- 提交门禁通过：`prek`（含 `ruff`、`ruff-format`）。

### d. Review 结论（2026-04-05）

- **逗号分隔符**：保留 `,` 作为规则分隔符，与 `limits` 库语法兼容（`limits` 使用 `[,;|]`），`"1,000/s"` 歧义在实际场景中不成立。
- **类型注解**：`cast()` 调用源于 `RateLimiterP` 联合类型，建议用 `Generic[_LimiterT, _HookT]` 参数化 `BaseThrottledMixin`，消除全部 4 处 `cast()`。拆分为独立 PR。
- **burst 语法**：当前 `burst=<n>` 用 `;` 分隔与规则分隔符语义冲突，改为关键字空格 `<rate> burst <n>`。调研了 nginx、Envoy、redis-cell、Traefik 等系统，均将 burst 与 rate 分离表达。

### e. 风险与后续

- 当前限制：`Throttled` 仍不支持多规则执行，仅解析层支持多规则表达。
- 后续：落地多规则执行模型，并补齐跨 store 一致性测试。
- 后续：burst 语法改造（关键字空格方案），合并为单正则解析。
- 后续：`BaseThrottledMixin` Generic TypeVar 重构，消除 `cast()` 调用。
- 说明：pre-commit 与类型检查调整已拆分到独立分支。

### f. 版本锚点

- 分支：`feat/260405_quota_parser_dsl`
- 提交：`e43b340`
- push 状态：已 push

## 0x06 实施进展（2026-04-06）

### a. 文档与示例收敛

- docs `quickstart/quota-configuration` 调整为 pattern-first 结构：
  - 明确 4 种字符串模式：`n / unit`、`n / unit burst <burst>`、`n per unit`、`n per unit burst <burst>`。
  - Quick Setup 中合并说明 `burst` 语义与生效算法，不再单独拆分段落。
  - 补充“标准单位 + 兼容写法”表，和 0x02 决策共识保持一致。
- docs 示例不再重复手写代码，统一通过 `literalinclude` 引用：
  - `examples/quickstart/quota_dsl_example.py`
  - `examples/quickstart/async/quota_dsl_example.py`
  - `examples/quickstart/quota_example.py`
- `examples/quickstart`（含 async）中 quota 写法统一为字符串模式；`quota_example.py` 作为“字符串不足时的对象构造”示例保留。

### b. README 收敛

- `README.md` / `README_ZH.md` 的 “Quota Configuration / 指定容量” 区块改为字符串配置主路径。
- 文案明确 `unit` 支持 `s / m / h / d / w`，并保留 4 种模式示例。
- 清理与 quota 字符串不一致的旧写法及冗余导入。

### c. 构建与修复

- 修复 Sphinx 报错：`Malformed table`。
  - 将 `quota-configuration.rst` 的网格表改为 `list-table`，避免列宽/对齐引发解析失败。
- 修复文案细节：
  - `README.md`：`for:` 后补空格。
  - `README_ZH.md`：`TOEKN_BUCKET` 更正为 `TOKEN_BUCKET`。

### d. 验证结论

- `uv run make html`：构建通过。
- `literalinclude` 目标文件存在性校验通过（无引用丢失）。
- 增量门禁校验通过：`prek --files`（`ruff` / `ruff-format` / `mypy-strict`）。
