---
title: 日志 UnifyQuery 环境变量白名单与 query_string 增强 —— 实施方案
tags: [log, unify-query, data-source, query-string, config]
issue: ./README.md
description: 为日志灰度白名单增加环境变量配置层，并在日志数据源中对齐日志平台 query_string 处理逻辑
created: 2026-03-05
updated: 2026-03-05
---

# 日志 UnifyQuery 环境变量白名单与 query_string 增强 —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 实现方案

### a. 白名单优先级

**Before**：`_fetch_white_list` 两层——类成员（对账覆盖） > DB 动态配置。

**After**：三层——类成员 > 环境变量 > DB。

- 环境变量在 `config/default.py` 声明，命名区别于 DB 配置项（如 `_ENV` 后缀）。
- 从 `os.getenv` 解析逗号分隔业务 ID。

### b. query_string 模板方法

**Before**：`BaseBkMonitorLogDataSource.to_unify_query_config` 中 `"query_string": self.query_string or "*"` 内联，子类无法定制。

**After**：提取 `_get_unify_query_string` 模板方法。

- 基类保持原有语义。
- `LogSearchTimeSeriesDataSource` 覆写，对齐日志平台 QueryStringBuilder 核心逻辑：
  - HTML 反转义 → 特殊字符检查 → 通配符包裹。
  - 简化为单个方法，正则和通配符作为类常量。

> 日志平台参考：[query_string_builder.py](https://github.com/TencentBlueKing/bk-monitor/blob/master/bklog/apps/log_esquery/esquery/builder/query_string_builder.py#L46)

## 0x02 开发方案

### a. 环境变量配置

`config/default.py` — 在 `LOG_UNIFY_QUERY_WHITE_BIZ_LIST` 附近新增配置项。

- 从环境变量解析逗号分隔整数列表，未设置时为空列表。
- 格式：`LOG_UNIFY_QUERY_WHITE_BIZ_LIST=2,9,100147,-50`

### b. `BaseBkMonitorLogDataSource`

`bkmonitor/data_source/data_source/__init__.py`

- `_get_unify_query_string`：新增，用于自定义 `query_string`。
- `to_unify_query_config`：`query_string` 改为调用 `self._get_unify_query_string()`。

### c. `LogSearchTimeSeriesDataSource`

`bkmonitor/data_source/data_source/__init__.py`

- 通配符常量、特殊字符正则：新增类常量，预编译。
- `_fetch_white_list`：新增环境变量优先级层。
- `_get_unify_query_string`：覆写，对齐日志平台 QueryStringBuilder。

### d. Helm 灰度配置

`bk-monitor-helm-values` — `monitor.extraEnvVars`


| 环境   | 灰度业务                 |
| ---- | -------------------- |
| bkte | 100147               |
| bkop | 2, 9, 10, 11, 7, -50 |


同步到本地开发环境 `local/env/bkop.woa.com.env`。


## 0x03 Review 要点

### a. 白名单变量来源

日志策略是否走 UnifyQuery 查询由白名单控制，业务命中白名单则走 UnifyQuery，否则走原有日志平台 API。

- DB 动态配置（GlobalConfig）暂未接入，待灰度验证通过后再开放。
- 当前仅使用**环境变量** `LOG_UNIFY_QUERY_WHITE_BIZ_LIST` 控制灰度，逗号分隔业务 ID。
- 环境变量不可热更，变更需重启服务。

`bkmonitor/data_source/data_source/__init__.py`：

```python
class LogSearchTimeSeriesDataSource(BaseBkMonitorLogDataSource):

  # 用于灰度对账的临时白名单列表（类成员变量），仅终端生效，运行时恒定为 None。
  LOG_UNIFY_QUERY_WHITE_BIZ_LIST: list[int] | None = None

  @classmethod
  def _fetch_white_list(cls) -> list[str | int]:
      # 🌟 仅用于命令行对账，线上环境恒定为 None，没有引用设置该变量的入口。
      if cls.LOG_UNIFY_QUERY_WHITE_BIZ_LIST is not None:
          return cls.LOG_UNIFY_QUERY_WHITE_BIZ_LIST

      return settings.LOG_UNIFY_QUERY_WHITE_BIZ_LIST_ENV
```

`config/default.py`：

```python
# 日志 UnifyQuery 查询业务白名单（环境变量，逗号分隔业务 ID）
_log_uq_white_biz_env = os.getenv("LOG_UNIFY_QUERY_WHITE_BIZ_LIST", "")
LOG_UNIFY_QUERY_WHITE_BIZ_LIST_ENV = (
    [int(biz_id.strip()) for biz_id in _log_uq_white_biz_env.split(",") if biz_id.strip()]
    if _log_uq_white_biz_env
    else []
)
```

### b. Helm 配置

在 `bk-monitor-helm-values` 的 `monitor.extraEnvVars` 中新增：

**bkte** (`bkte/bkmonitor-values.yaml`)：

```yaml
- name: LOG_UNIFY_QUERY_WHITE_BIZ_LIST
  value: "100147,100791"
```

**bkop** (`bkop/bkmonitor-values.yaml`)：

```yaml
- name: LOG_UNIFY_QUERY_WHITE_BIZ_LIST
  value: "2,9,10,11,7,-50"
```

Helm values 已提前设置，代码发布后立即生效。

### c. 风险

- **影响范围**：仅命中白名单的业务受影响，未命中的业务行为不变。
- **query_string 处理对齐**：切换 UnifyQuery 后绕过日志平台，新增了日志平台原有的 query_string 预处理（HTML 反转义、通配符包裹），确保查询行为一致。

---

*制定日期：2026-03-05*