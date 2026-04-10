---
title: APM 返回码重定义规则清空不生效 —— 实施方案
tags: [apm, code-redefine, code-relabel, config-refresh]
issue: ./README.md
description: 通过修复发布层对空列表的语义识别，消除 APM 返回码重定义的旧配置残留
created: 2026-04-10
updated: 2026-04-10
---

# APM 返回码重定义规则清空不生效 —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 调研与约束

### a. 根因

空规则落库与聚合为 `[]` 都符合预期。真正的问题是发布层把
“字段缺省”和“显式空列表”都当成“不处理”，导致旧的
`CODE_RELABEL_CONFIG` 没有被删除。*[a]* *[b]* *[c]*

### b. 约束

- 不改前端协议。
- 不改 `build_code_relabel_config` 的聚合语义。
- 删除动作只能精确命中 `type=CODE_RELABEL_CONFIG`。

## 0x02 方案主干

### a. 语义分流

把 `code_relabel_config` 从“默认 `[]`”调整为“默认缺省”：

- `None`：本次未更新该字段，跳过。
- `[]`：本次明确清空，删除旧配置。
- 非空列表：覆盖更新。

### b. 删除策略

清空时不复用
`refresh_config(..., need_delete_config=True)`，
而是按当前应用和 `type=CODE_RELABEL_CONFIG`
做精确删除，避免误删其他应用级配置。*[b]*

### c. 测试落点

| 文件 | 验证重点 |
| ---- | ---- |
| `apm/tests/test_release_app_config.py` | 缺省、空列表、非空列表三种输入的行为分流。 |
| `apm/tests/storage/test_normal_type_value_config.py` | 精确删除只影响 `CODE_RELABEL_CONFIG`。 |

## 0x03 实施步骤

1. 调整 `ReleaseAppConfigResource.RequestSerializer` 的缺省值语义。
2. 调整 `set_code_relabel_config` 的三态处理。
3. 补齐资源层与存储层测试。
4. 回归清空规则与非相关配置更新场景。

## 0x04 验收与验证

- 清空唯一规则后，`CODE_RELABEL_CONFIG` 被删除。
- `ApplicationConfig.get_metrics_filter_config()` 返回空对象。*[c]*
- 更新其他应用配置但未传 `code_relabel_config` 时，不影响已有返回码重定义配置。
- 删除返回码重定义配置不会影响其他 `NormalTypeValueConfig` 类型。

## 0x05 实施进展

| 时间 | 对应设计片段 | 结论调整概要 | 改动 / 验证 |
| ---- | ---- | ---- | ---- |
| `2026-04-10 16:00` | `0x01.a` `0x02.a` `0x02.b` | [1] 收敛为发布层单点修复<br />[2] 不调整前端和聚合逻辑 | [1] 已完成代码阅读与方案收敛<br />[2] 代码尚未实施 |

## 0x06 参考

*[a]* 发布入口：`packages/apm_web/service/resources.py`

*[b]* 发布落库：`apm/resources.py`

*[c]* 配置读取：`apm/core/application_config.py`

## 0x07 版本锚点

- 分支：`待定`
- PR：`待定`
