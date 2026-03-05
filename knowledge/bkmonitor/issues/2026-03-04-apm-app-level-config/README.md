---
title: APM 支持应用级别配置
tags: [apm, service-config, log-relation, code-redefine, app-level]
description: 将 APM 服务关联配置（日志关联、返回码重定义）从纯服务粒度扩展到应用级别，支持跨服务共享与全局配置
created: 2026-03-04
updated: 2026-03-04
---

# APM 支持应用级别配置

## 0x01 背景

### a. Why

当前 APM 的服务关联配置（日志关联、返回码重定义等）全部以 `(bk_biz_id, app_name, service_name)` 为粒度，没有"应用级别"或"跨服务共享"的概念。用户想为应用下所有服务设置统一日志关联或统一返回码规则时，只能逐服务手动配置，成本高且易遗漏。

### b. 目标

- 支持应用级别（全局）的日志关联和返回码重定义配置
- 支持指定服务列表作为配置生效范围，而不仅是单个服务
- 全局配置与服务级配置可共存，服务级优先（覆盖语义）

## 0x02 需求

### a. 基础能力：ServiceBase 跨服务关联

1. 新增"生效范围"字段（`service_names`，JSONField），表示该配置作用的服务列表
2. 约定全局表示方式（如空列表 `[]` = 全局）
3. 获取关联信息统一收口：按 `(bk_biz_id, app_name, service_names, 是否包含全局)` 查询
4. 数据迁移：`service_name` → `service_names`，第一期确保创建时准确注入

### b. 日志关联全局改造（LogServiceRelation）

1. `SetupResource`：支持应用级别日志关联写入
2. `ApplicationInfoByAppNameResource`：支持应用级别日志关联查询展示
3. `ServiceLogHandler.get_log_relations`：改为调用基础能力的统一查询接口，收敛所有 `(bk_biz_id, app_name, service_names)` 模式的查询

### c. 返回码重定义全局改造（CodeRedefinedConfigRelation）

1. `ListCodeRedefinedRuleResource`：增加全局、跨服务共享规则展示
2. `SetCodeRedefinedRuleResource`：生成配置时，合并全局、跨服务共享规则

### d. 待确认

- `ServiceConfigResource`：服务级别界面是否展示全局关联？是否可编辑全局/共享规则？

## 0x03 参考

- 实施方案：[PLAN.md](./PLAN.md)
- 返回码重定义代码片段：`knowledge/bkmonitor/snippets/apm-code-redefine.md`
