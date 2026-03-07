---
title: 日志 UnifyQuery 环境变量白名单与 query_string 增强
tags: [log, unify-query, data-source, query-string, config]
description: 为日志 UnifyQuery 灰度白名单增加环境变量配置层，并对齐日志平台 query_string 处理逻辑
created: 2026-03-05
updated: 2026-03-05
---

# 日志 UnifyQuery 环境变量白名单与 query_string 增强

## 0x01 背景

### a. Why

- 日志数据源切换 UnifyQuery 采用灰度白名单（`LOG_UNIFY_QUERY_WHITE_BIZ_LIST`）。
- 当前只能通过 DB 动态配置设置，灰度发布需登录管理后台，不利于按环境差异化管控。
- 需要增加环境变量配置层，部署时通过 Helm values 注入即可。

此外：

- 切换 UnifyQuery 后绕过了日志平台 API。
- 日志平台对 `query_string` 的预处理（HTML 反转义、通配符包裹）缺失，可能导致查询行为不一致。

### b. 目标

- 环境变量 `LOG_UNIFY_QUERY_WHITE_BIZ_LIST` 支持灰度白名单，优先级高于 DB。
- `LogSearchTimeSeriesDataSource` 对齐日志平台的 `query_string` 处理。
- 抽象 `_get_unify_query_string` 方法，允许日志数据源子类定制。

## 0x02 实现路线

### a. 建议的方案

1. `config/default.py` 增加环境变量配置，命名区别于 DB 配置项。
2. `LogSearchTimeSeriesDataSource._fetch_white_list` 增加环境变量优先级。
3. `BaseBkMonitorLogDataSource.to_unify_query_config` 中 `self.query_string` 的处理抽象为 `_get_unify_query_string`，允许子类定制。
4. `LogSearchTimeSeriesDataSource` 覆写 `_get_unify_query_string`，参考日志平台 QueryStringBuilder 对齐处理逻辑，简化为单个方法。

### b. 约束

- 基类默认行为不变（`self.query_string or "*"`）。
- 参考日志平台 QueryStringBuilder 实现，但简化为单个方法而非独立类。

## 0x03 参考

- 前置需求：`knowledge/bkmonitor/issues/2026-02-10-log-ds-to-unify-query/`
- 日志平台 QueryStringBuilder：[bklog query_string_builder.py](https://github.com/TencentBlueKing/bk-monitor/blob/master/bklog/apps/log_esquery/esquery/builder/query_string_builder.py#L46)
- 实施方案：[PLAN.md](./PLAN.md)
