---
title: 日志 UnifyQuery 环境变量黑名单与 query_string 增强 —— 实施方案
tags: [log, unify-query, data-source, query-string, config, blacklist]
issue: ./README.md
description: 日志查询默认切换到 UnifyQuery，以环境变量黑名单控制业务回退，并保留 query_string 兼容处理
created: 2026-03-05
updated: 2026-07-21
---

# 日志 UnifyQuery 环境变量黑名单与 query_string 增强 —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 实现方案

### a. 黑名单路由

普通日志查询默认使用 UnifyQuery，环境变量黑名单只表达需要回退到日志平台数据源的业务。

- `LOG_UNIFY_QUERY_BLACK_BIZ_LIST` 保存逗号分隔的业务 ID，未配置时为空列表。
- `LOG_UNIFY_QUERY_BLACK_BIZ_LIST` 类成员只用于对账命令临时覆盖，值为 `None` 时读取环境变量。
- `switch_unify_query` 先处理全局数据源开关和聚类表，再判断业务是否命中黑名单。
- 命中黑名单返回 `False`，未命中返回 `True`，业务 ID 同时兼容整数与字符串形式。
- DB 动态配置不再参与日志查询路由，删除未生效的旧白名单配置项。

### b. query_string 模板方法

**Before**：`BaseBkMonitorLogDataSource.to_unify_query_config` 中 `"query_string": self.query_string or "*"` 内联，子类无法定制。

**After**：提取 `_get_unify_query_string` 模板方法。

- 基类保持原有语义。
- `LogSearchTimeSeriesDataSource` 覆写，对齐日志平台 QueryStringBuilder 核心逻辑：
  - HTML 反转义 → 特殊字符检查 → 通配符包裹。
  - 简化为单个方法，正则和通配符作为类常量。

> 日志平台参考：[query_string_builder.py](https://github.com/TencentBlueKing/bk-monitor/blob/master/bklog/apps/log_esquery/esquery/builder/query_string_builder.py#L46)

### c. 聚类表路由

日志聚类查询的表后缀 `_clustered` 是查询能力边界：命中聚类表时不受业务黑名单影响，统一使用 UnifyQuery 查询。

后缀判断从 `_get_unify_query_table` 拆为 `_get_unify_query_table_suffix`，由表名拼接和 `switch_unify_query` 共用，避免两处维护聚类识别规则。

## 0x02 开发方案

### a. 环境变量配置

`config/default.py` 声明 `LOG_UNIFY_QUERY_BLACK_BIZ_LIST_ENV`：

- 从环境变量解析逗号分隔整数列表，未设置时为空列表。
- 配置格式：`LOG_UNIFY_QUERY_BLACK_BIZ_LIST=2,9,100147,-50`。
- 删除旧的 `LOG_UNIFY_QUERY_WHITE_BIZ_LIST` 环境变量和未接入查询路由的 GlobalConfig 配置项。

### b. `BaseBkMonitorLogDataSource` 改造

`bkmonitor/data_source/data_source/__init__.py`

- `_get_unify_query_string`：新增，用于自定义 `query_string`。
- `to_unify_query_config`：`query_string` 改为调用 `self._get_unify_query_string()`。

### c. `LogSearchTimeSeriesDataSource` 改造

`bkmonitor/data_source/data_source/__init__.py`

- `[Change] LOG_UNIFY_QUERY_BLACK_BIZ_LIST`：保存对账命令的进程内临时覆盖值。
- `[Change] _fetch_black_list`：优先返回临时覆盖值，否则读取 `LOG_UNIFY_QUERY_BLACK_BIZ_LIST_ENV`。
- `[Change] switch_unify_query`：全局数据源和聚类表固定使用 UnifyQuery，普通日志按黑名单返回查询路径。
- `[Keep] _get_unify_query_table_suffix`：继续统一识别 `__dist` 聚类查询。
- `[Keep] _get_unify_query_string`：继续对齐日志平台 QueryStringBuilder。

### d. 对账命令

`bkmonitor/management/commands/reconcile_log_strategy.py` 通过类成员覆盖黑名单：

- `use_unify_query=True` 时设置空黑名单，强制普通日志使用 UnifyQuery。
- `use_unify_query=False` 时把当前业务 ID 加入黑名单，强制普通日志使用日志平台数据源。
- 数据源必须在设置临时黑名单后构建，查询结束后在 `finally` 中恢复为 `None`。

### e. 部署配置

`bk-monitor-helm-values` 的 `monitor.extraEnvVars` 使用 `LOG_UNIFY_QUERY_BLACK_BIZ_LIST`：

- `bkte` 配置 `5000206,622`，分别回退 TAM 前端监控和 TGlog。
- `bkop` 删除旧白名单，不配置黑名单；其他环境也不配置黑名单，默认使用 UnifyQuery。
- 环境变量不可热更新，变更后需要重启服务。

## 0x03 验收、Review 与风险结论

### a. 验收口径

- 空黑名单：普通日志使用 UnifyQuery。
- 业务 ID 以整数或字符串形式命中黑名单：普通日志使用日志平台数据源。
- 未命中黑名单：普通日志使用 UnifyQuery。
- 负数业务 ID 命中黑名单：普通日志使用日志平台数据源。
- 聚类查询命中黑名单：仍使用 UnifyQuery。
- 对账临时黑名单优先于环境变量，并在查询结束后恢复。

### b. Review 结论

- [TencentBlueKing/bk-monitor #11599](https://github.com/TencentBlueKing/bk-monitor/pull/11599) 已于 `2026-07-21 19:42` 合入 `master`，合并提交为 `35c429eaf7a178b052809026c794b136e037c5be`。
- 黑名单命名、对账覆盖、`switch_unify_query` 路由和单元测试与本方案一致。
- `8` 个定向测试通过，Ruff 与 `git diff --check` 通过。

### c. 行为风险

- 高风险：代码和 Helm 配置必须按同一版本生效。旧代码只读取白名单，提前删除白名单会让普通日志回退到日志平台；新代码若先于黑名单配置生效，则 TAM 前端监控和 TGlog 会短暂使用 UnifyQuery。
- 中风险：业务黑名单只控制普通日志路由。聚类查询固定使用 UnifyQuery，表达式、查询函数或多数据源等强制 UnifyQuery 场景也可能绕过 `switch_unify_query`。
- 高风险：除 `bkte` 外不配置黑名单会放开所有普通日志查询。`bkop` 原白名单为 `-1`，切换后语义不变；原先未配置白名单的环境会从日志平台数据源整体切到 UnifyQuery。
- 中风险：黑名单没有 DB 动态配置，调整后需要重启服务。发布后需重点观察 UnifyQuery 请求量、错误率、耗时和两条查询路径的对账结果。

## 0x06 实施进展

| 时间 | 结论性进展 |
| --- | --- |
| `2026-07-21 19:00` | [a] [TencentBlueKing/bk-monitor #11599](https://github.com/TencentBlueKing/bk-monitor/pull/11599) 已合入 `master`<br />[b] `bk-monitor-helm-values` 已同步到 `48428cf9`，删除旧白名单，`bkte` 为 TAM 前端监控和 TGlog 配置黑名单，其他环境默认使用 UnifyQuery<br />[c] 确认代码与 Helm 配置需同版本生效，并保留聚类及强制 UnifyQuery 场景绕过黑名单的风险提示 |
| `2026-06-10 15:00` | 日志聚类查询统一走 UnifyQuery 的实现已通过 [TencentBlueKing/bk-monitor #11010](https://github.com/TencentBlueKing/bk-monitor/pull/11010) 合入 `master`。变更覆盖数据源路由和对应单测 |
| `2026-06-08 14:00` | [a] 确认初始落地 PR 为 [TencentBlueKing/bk-monitor #9086](https://github.com/TencentBlueKing/bk-monitor/pull/9086)，当前全量灰度扩展 PR 为 [TencentBlueKing/bk-monitor #10966](https://github.com/TencentBlueKing/bk-monitor/pull/10966)<br />[b] 全量灰度保持在 `switch_unify_query` 原判断结构内扩展，先判断 `-1` / `"-1"` 全量标识，再执行原业务白名单判断 |
| `2026-03-05 21:00` | 完成日志数据源切换 UnifyQuery、环境变量灰度白名单和 query_string 对齐能力合入 |

## 0x07 参考 & 版本锚点

| 状态 | 分支 | 里程碑 | PR |
| --- | --- | --- | --- |
| ✅ | `feat/event/#1010158081129076973` | 里程碑 1：日志数据源切换 UnifyQuery 与灰度白名单 | [TencentBlueKing/bk-monitor #9086](https://github.com/TencentBlueKing/bk-monitor/pull/9086) |
| ✅ | `feat/datasource/#1010158081135015922` | 里程碑 2：日志数据源全量灰度标识 | [TencentBlueKing/bk-monitor #10966](https://github.com/TencentBlueKing/bk-monitor/pull/10966) |
| ✅ | `feat/datasource/#1010158081135097674` | 里程碑 3：日志聚类场景统一通过 UnifyQuery 查询 | [TencentBlueKing/bk-monitor #11010](https://github.com/TencentBlueKing/bk-monitor/pull/11010) |
| ✅ | `feat/log_unify_query_switch_black_biz_list/#1010158081136300803` | 里程碑 4：日志 UnifyQuery 灰度切换改为业务黑名单 | [TencentBlueKing/bk-monitor #11599](https://github.com/TencentBlueKing/bk-monitor/pull/11599) |
| 🔄 | `master` | 里程碑 5：按环境收敛 Helm 白名单并配置 `bkte` 回退业务 | 待创建 |

---

*制定日期：2026-03-05*
