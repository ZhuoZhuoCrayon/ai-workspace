---
title: 日志 UnifyQuery 环境变量白名单与 query_string 增强 —— 实施方案
tags: [log, unify-query, data-source, query-string, config]
issue: ./README.md
description: 为日志灰度白名单增加环境变量配置层，并在日志数据源中对齐日志平台 query_string 处理逻辑
created: 2026-03-05
updated: 2026-06-08
---

# 日志 UnifyQuery 环境变量白名单与 query_string 增强 —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 实现方案

### a. 白名单优先级

**Before**：`_fetch_white_list` 两层——类成员（对账覆盖） > DB 动态配置。

**After**：三层——类成员 > 环境变量 > DB。

- 环境变量在 `config/default.py` 声明，命名区别于 DB 配置项（如 `_ENV` 后缀）。
- 从 `os.getenv` 解析逗号分隔业务 ID。
- 白名单判断保持原 `switch_unify_query` 结构，仅在原有业务 ID / 字符串业务 ID 命中基础上扩展 `-1` / `"-1"` 全量灰度标识。
- `-1` 作为全量灰度标识，只要出现在白名单中，任意业务均走 UnifyQuery。

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
- 全量灰度格式：`LOG_UNIFY_QUERY_WHITE_BIZ_LIST=-1`

### b. `BaseBkMonitorLogDataSource`

`bkmonitor/data_source/data_source/__init__.py`

- `_get_unify_query_string`：新增，用于自定义 `query_string`。
- `to_unify_query_config`：`query_string` 改为调用 `self._get_unify_query_string()`。

### c. `LogSearchTimeSeriesDataSource`

`bkmonitor/data_source/data_source/__init__.py`

- 通配符常量、特殊字符正则：新增类常量，预编译。
- 全量灰度常量：新增 `LOG_UNIFY_QUERY_ALL_BIZ_ID = -1`。
- `_fetch_white_list`：新增环境变量优先级层。
- `switch_unify_query`：保持原判断结构，将 `-1` / `"-1"` 全量灰度判断作为独立分支，再执行原有业务 ID / 字符串业务 ID 命中判断。
- `_get_unify_query_string`：覆写，对齐日志平台 QueryStringBuilder。

### d. Helm 灰度配置

`bk-monitor-helm-values` — `monitor.extraEnvVars`


| 环境   | 灰度业务                 |
| ---- | -------------------- |
| bkte | 100147               |
| bkop | 2, 9, 10, 11, 7, -50 |

全量灰度配置规则：

- 需要全量灰度时配置为 `-1`。
- `-1` 可以与局部业务 ID 共存，命中后局部业务 ID 不再影响判断结果。


同步到本地开发环境 `local/env/bkop.woa.com.env`。


## 0x03 Review 要点

### a. 白名单变量来源

日志策略是否走 UnifyQuery 查询由白名单控制，业务命中白名单则走 UnifyQuery，否则走原有日志平台 API。

- DB 动态配置（GlobalConfig）暂未接入，待灰度验证通过后再开放。
- 当前仅使用**环境变量** `LOG_UNIFY_QUERY_WHITE_BIZ_LIST` 控制灰度，逗号分隔业务 ID。
- 当前白名单支持 `-1` 全量灰度标识。
- 只要列表中存在 `-1`，所有业务都视为命中。
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

  def switch_unify_query(self, bk_biz_id: int) -> bool:
      white_list = self._fetch_white_list()
      if self.LOG_UNIFY_QUERY_ALL_BIZ_ID in white_list or str(self.LOG_UNIFY_QUERY_ALL_BIZ_ID) in white_list:
          return True

      if bk_biz_id in white_list or str(bk_biz_id) in white_list:
          return True
      return False
```

`config/default.py`：

```python
# 日志 UnifyQuery 查询业务白名单（环境变量，逗号分隔业务 ID，-1 表示全量灰度）
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
- **全量灰度**：`-1` 会扩大影响范围到所有业务，应只在明确需要全量切换时配置。
- **query_string 处理对齐**：切换 UnifyQuery 后绕过日志平台，新增了日志平台原有的 query_string 预处理（HTML 反转义、通配符包裹），确保查询行为一致。

## 0x06 实施进展

| 时间 | 结论性进展 |
| --- | --- |
| `2026-06-08 14:00` | [a] 确认初始落地 PR 为 [TencentBlueKing/bk-monitor #9086](https://github.com/TencentBlueKing/bk-monitor/pull/9086)，当前全量灰度扩展 PR 为 [TencentBlueKing/bk-monitor #10966](https://github.com/TencentBlueKing/bk-monitor/pull/10966)<br />[b] 全量灰度保持在 `switch_unify_query` 原判断结构内扩展，先判断 `-1` / `"-1"` 全量标识，再执行原业务白名单判断 |
| `2026-03-05 21:00` | 完成日志数据源切换 UnifyQuery、环境变量灰度白名单和 query_string 对齐能力合入 |

## 0x07 参考 & 版本锚点

| 状态 | 分支 | 里程碑 | PR |
| --- | --- | --- | --- |
| ✅ | `feat/event/#1010158081129076973` | 里程碑 1：日志数据源切换 UnifyQuery 与灰度白名单 | [TencentBlueKing/bk-monitor #9086](https://github.com/TencentBlueKing/bk-monitor/pull/9086) |
| ✅ | `feat/datasource/#1010158081135015922` | 里程碑 2：日志数据源全量灰度标识 | [TencentBlueKing/bk-monitor #10966](https://github.com/TencentBlueKing/bk-monitor/pull/10966) |

---

*制定日期：2026-03-05*
