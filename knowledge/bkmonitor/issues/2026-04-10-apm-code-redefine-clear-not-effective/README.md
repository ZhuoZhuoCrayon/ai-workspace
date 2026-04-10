---
title: APM 返回码重定义规则清空不生效
tags: [apm, code-redefine, code-relabel, config-refresh]
description: 修复 APM 返回码重定义在清空保存后未同步删除下游配置的问题
created: 2026-04-10
updated: 2026-04-10
---

# APM 返回码重定义规则清空不生效

## 0x01 背景

### a. 现象

返回码重定义规则清空后，页面展示已变为
`{"success": "", "timeout": "", "exception": ""}`，
且聚合结果为 `[]`。
这两步都符合“当前无有效规则”的预期。

### b. 问题

后台发布链路没有把显式空列表解释为“删除已有
`code_relabel_config`”，导致采集端继续使用历史配置。

### c. 目标

- 保持前端现有清空表达不变。
- 保持聚合结果为 `[]` 的现有行为不变。
- 修复发布链路，让“显式清空”真正删除下游旧配置。

## 0x02 实现路线

### a. 建议方案

- 在发布层区分“字段缺省”和“显式空列表”。
- `None` 表示本次未更新返回码重定义配置。
- `[]` 表示明确清空，需删除当前应用的
  `ConfigTypes.CODE_RELABEL_CONFIG`。
- 非空列表继续按现有逻辑覆盖更新。

### b. 约束

- 不能把问题转移到前端协议。
- 不能直接使用
  `NormalTypeValueConfig.refresh_config(..., need_delete_config=True)`，
  否则会误删同一应用下其他 `type` 配置。

## 0x03 参考

- 实施方案：[PLAN.md](./PLAN.md)
- 关联需求：[APM 支持应用级别配置](../2026-03-04-apm-app-level-config/README.md)
- 代码片段：[APM 返回码重定义](../../snippets/apm-code-redefine.md)

*[a]* 发布入口：`packages/apm_web/service/resources.py`

*[b]* 发布落库：`apm/resources.py`

*[c]* 配置读取：`apm/core/application_config.py`
