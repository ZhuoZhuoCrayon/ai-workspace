---
title: 日志 UnifyQuery 环境变量黑名单与 query_string 增强
tags: [log, unify-query, data-source, query-string, config, blacklist]
description: 日志查询默认切换到 UnifyQuery，通过环境变量黑名单保留按业务回退能力，并对齐 query_string 处理逻辑
created: 2026-03-05
updated: 2026-07-21
---

# 日志 UnifyQuery 环境变量黑名单与 query_string 增强

## 0x01 背景

### a. Why

- 日志数据源已完成 UnifyQuery 白名单灰度验证，后续应默认使用 UnifyQuery。
- 部分业务仍需保留回退到日志平台数据源的能力，灰度控制应从白名单改为环境变量黑名单。
- 对账命令需要在同一进程内强制切换两条查询路径，不能受线上黑名单配置影响。

切换 UnifyQuery 后会绕过日志平台 API，因此仍需保留已落地的 `query_string` 预处理，避免两条查询路径行为不一致。

### b. 目标

- 环境变量 `LOG_UNIFY_QUERY_BLACK_BIZ_LIST` 指定回退业务：命中黑名单时使用日志平台数据源，其他业务默认使用 UnifyQuery。
- 对账命令、`switch_unify_query` 和单元测试统一采用黑名单语义。
- 保持聚类查询固定使用 UnifyQuery，并保留日志平台 `query_string` 预处理语义。

## 0x02 实现路线

### a. 建议的方案

1. 将环境变量改为 `LOG_UNIFY_QUERY_BLACK_BIZ_LIST`，解析逗号分隔的业务 ID。
2. `LogSearchTimeSeriesDataSource` 统一通过 `_fetch_black_list` 读取对账临时值或环境变量。
3. `switch_unify_query` 保持全局数据源开关和聚类表优先，再按黑名单决定普通日志查询路径。
4. 对账命令以空黑名单强制使用 UnifyQuery，以当前业务 ID 黑名单强制使用日志平台数据源，并在查询结束后恢复默认状态。

### b. 约束

- 聚类表查询不受业务黑名单影响，始终使用 UnifyQuery。
- 黑名单只通过环境变量配置，不接入 DB 动态配置，配置变更需重启服务。
- 基类 `query_string` 默认行为和日志数据源的 HTML 反转义、通配符包裹逻辑保持不变。

## 0x03 参考

- 前置需求：`knowledge/bkmonitor/issues/2026-02-10-log-ds-to-unify-query/`
- 日志平台 QueryStringBuilder：[bklog query_string_builder.py](https://github.com/TencentBlueKing/bk-monitor/blob/master/bklog/apps/log_esquery/esquery/builder/query_string_builder.py#L46)
- 黑名单切换实现：[TencentBlueKing/bk-monitor #11599](https://github.com/TencentBlueKing/bk-monitor/pull/11599)
