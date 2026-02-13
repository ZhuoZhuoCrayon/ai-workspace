---
title: 日志数据源切换 unify-query
tags: [log, unify-query, data-source]
description: 将日志查询数据源从原有实现切换到 unify-query 统一查询层
created: 2026-02-10
updated: 2026-02-10
---

# 日志数据源切换 unify-query

## 0x01 背景

### a. Why

统一日志查询数据源到 unify-query，提升查询能力和可维护性。

### b. 目标

- 日志数据源切换到 unify-query 统一查询层
- 提供查询对账脚本验证切换正确性

## 0x02 实现路线

### a. 建议的方案

1. 重构 `data_source/__init__.py`，切换日志查询到 unify-query
2. 新增 `reconcile_log_strategy` 管理命令用于查询对账

### b. 约束

- 需保证切换后查询结果与原实现一致

## 0x03 参考

- 开发分支：`feat/log_ds_to_uq`
- 主实现：commit `d802715f`
- 对账脚本：commit `0806795b`
