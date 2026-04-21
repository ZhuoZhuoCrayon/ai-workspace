---
title: 优化 APM 接口统计偶现查询报错
tags: [apm, endpoint-stat, hot-window, aggregation, bucket-inconsistency]
description: 修复 APM endpoint 统计在热时间窗口内因聚合分桶不一致导致的接口报错
created: 2026-04-21
updated: 2026-04-21
---

# 优化 APM 接口统计偶现查询报错

## 0x01 背景

### a. 一句话结论

- endpoint 统计在热窗口尾部会收到不完整 bucket，Web 层又直接消费这些结果，因此同一接口会表现为 `division by zero` 与 `KeyError: 'sum_duration'` 两类随机报错。

### b. 现象分组

| 分组 | 代表样本 | 触发时机 | 直接表现 | 归类结论 |
| --- | --- | --- | --- | --- |
| 缺 `doc_count` | `6f2e515adc16f7fd0bfe6dc027602e70` | `end_time + 3s` | `division by zero` | 不完整 bucket 进入 URL 归类 |
| 缺 `sum_duration` | `7eaec8affe8e3491fd175ecb44580bdc` | `end_time + 0.22s` | `KeyError: 'sum_duration'` | 同一根因的另一症状 |
| 对照组 | `eeaa1bf235407915c8cb038c62e854a1` | 同窗口 `+20m32s` 重试 | 正常返回 | 数据沉淀后 bucket 完整 |

### c. 影响判断

- `query_apm_span` 与下游聚合请求整体成功，失败发生在 Web 层 URL 归类阶段。
- 问题不是单个 Trace 的偶发异常，而是热窗口下 bucket 完整性未收敛导致的接口级报错。
- 实时查询仍需保留，但返回给 Web 层的结果必须先完成完整性收敛。

### d. 目标

1. endpoint 统计接口在热时间窗口内不再因为不完整 bucket 报错。
2. 返回给 Web 层的 bucket 只保留指标完整的结果，保证单次请求内部自洽。
3. 保留实时查询能力，同时把热窗口的不完整数据收敛为“保守返回”而不是 `500`。

## 0x02 需求范围

- 在 `query_span_with_group_keys()` 返回前统一过滤缺少必要指标的 bucket。
- 修复 URL 归类统计对不完整 bucket 的处理方式。
- 修正当前实现中 URI 规则未按 `service_name` 生效的问题。
- 为热时间窗口补充验证与回归用例。

## 0x03 非目标

- 本期不重做 endpoint 统计的字段语义设计，例如 `http.route` / `http.url` 的全面迁移。
- 本期不调整 tracing 详情、span 检索或其他 APM 页面行为。
- 本期不通过“统一延后查询若干分钟”替代根因修复。

## 0x04 方法论

- 先按报错类型归类 Trace，再提炼共同触发条件与共同失败落点。
- 再对照本地代码确认 bucket 的生成、merge 与消费三个阶段的职责边界。
- 根因、修复路径与验证口径统一沉淀到 [PLAN.md](./PLAN.md)，`README.md` 只保留需求主干。

## 0x05 验收标准

- 同一接口在热时间窗口内不再出现 `division by zero` 或 `KeyError: 'sum_duration'`。
- 缺少任一必要指标的 bucket 会在返回 Web 层前被统一过滤。
- URL 归类统计只消费具备 `doc_count`、`avg_duration`、`max_duration`、`min_duration`、`sum_duration` 的 bucket。
- `service_name` 下的 URI 归类只使用该服务生效的 URI 规则。
- 补齐至少一组覆盖“缺 `doc_count`”与“缺 `sum_duration`”场景的自动化验证。

## 0x06 参考

- 实施方案：[PLAN.md](./PLAN.md)
- 相关排障：[endpoint stat 查询指定 SpanName 无数据](../../troubleshooting/endpoint-stat-no-data-for-http-server-span.md)
- 代码片段：[UnifyQuery 查询](../../snippets/unify-query.md)
- 证据样本：见 `0x01.b` 现象分组
