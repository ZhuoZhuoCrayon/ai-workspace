---
title: 【告警中心】APM 应用/服务页面嵌入列表页支持 —— 实施方案
tags: [alert, apm, embedded-list, frontend]
issue: ./README.md
description: 预设 Lucene query_string 实现 APM 视角告警列表嵌入，含接口协议与实现方案
created: 2026-03-19
updated: 2026-04-08

---

# 【告警中心】APM 应用/服务页面嵌入列表页支持 —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 实现方案

### a. 预设过滤条件生成

流程：

1. 调用预设过滤条件接口。
2. 按 `target_types` 路由生成各目标类型过滤片段：
   - `APM-SERVICE`：`target + labels` 片段；
   - `HOST`：`HostHandler` 产出 IP 目标片段；
   - `K8S-WORKLOAD`：`EntitySet` 产出 workload 标签片段。
3. 将各片段用 `OR` 拼接。
4. 输出 `query_string`，用于告警中心嵌入页。

**应用视角**（不传 `service_name`，不支持 `target_types`）：

```text
target: {app_name}\:* OR labels: "APM-APP({app_name})"
```

**服务视角**（传 `service_name`，按 `target_types` 组合，**各片段加括号后以 OR 拼接**）：

| target_type  | 过滤片段                                                     | 数据来源                             |
| ------------ | ------------------------------------------------------------ | ------------------------------------ |
| APM-SERVICE  | `(target: "{app_name}:{service_name}" OR labels: ("APM-APP({app_name})" AND "APM-SERVICE({service_name})"))` | 直接拼接                             |
| HOST         | `(target: ("{ip1}\|{cloud_id1}" OR "{ip2}\|{cloud_id2}" OR ...))` | `HostHandler.list_application_hosts` |
| K8S-WORKLOAD | `((tags.bcs_cluster_id: "{c1}" AND tags.workload_kind: "{k1}" AND tags.workload_name: "{n1}") OR (...))` | `EntitySet.get_workloads`            |

**时间范围限制**（HOST / K8S-WORKLOAD）：超过 2 小时取 `[end_time - 2h, end_time]`。

### b. 已关联策略

流程：

1. 服务页以 `labels` 过滤调用 `FetchItemStatus`。
2. 返回策略数与告警数，展示“该服务已关联 N 个告警策略”。
3. 点击后跳转策略列表页，并带入对应筛选条件。

- 请求 `FetchItemStatus`：`metric_ids=[]`，`labels=["APM-APP({app_name})", "APM-SERVICE({service_name})"]`
- 跳转策略列表页：`conditions=[{"key": "label_name", "value": ["/APM-SERVICE({service_name})/"]}]`

### c. conditions → query_string 转换接口（告警列表 UI 模式）

为支持 APM 嵌入页将 UI 模式查询条件并入内置条件，需要补一个“`conditions` 转 Lucene `query_string`”接口。

转换链路（无额外字段转换）：

1. 读取 `conditions[]`（`key/value/method/condition`）。
2. 对每条条件调用 `QueryStringGenerator` 生成单条件片段。
3. 按 `condition`（and/or）将片段折叠为整体表达式。
4. 输出 `query_string`。

核心约束：

- 参数结构与 `AlertSearchSerializer.conditions` 对齐（`key/value/method/condition`）。
- 操作符映射复用 `QueryStringGenerator`：
  - `eq -> equal`
  - `neq -> not_equal`
  - `include -> include`
  - `exclude -> not_include`
  - `gt/gte/lt/lte -> gt/gte/lt/lte`
- 条件间关系按 `condition` 折叠：
  - `or`：OR 连接
  - `and` / `""`：AND 连接
  - 首个条件的 `condition` 忽略（作为起始表达式）
- 空 `conditions` 返回空字符串 `""`。

### d. 代码变更

| 变更              | 文件                                         | 说明                                                         |
| ----------------- | -------------------------------------------- | ------------------------------------------------------------ |
| 标签常量收归      | `constants/apm.py`                           | `ApmAlertHelper` 新增 `APM_APP_LABEL_FORMAT` / `APM_SERVICE_LABEL_FORMAT` 及格式化方法 |
| 引用常量          | `apm_web/strategy/dispatch/builder.py`       | `build()` 中替换硬编码字面量                                 |
| 容器关联下沉      | `apm_web/strategy/dispatch/`                 | 新增工具函数封装 `EntitySet.get_workloads`，供新接口调用     |
| 新增接口          | `apm_web/strategy/views.py`                  | 预设过滤条件接口                                             |
| metric_ids 非必填 | `monitor_web/strategies/resources/public.py` | `FetchItemStatus.RequestSerializer` 中 `metric_ids` 改为 `required=False, default=[]` |
| 新增资源          | `fta_web/alert/resources.py`                 | 新增 `GenerateQueryString` 资源：输入 `conditions`，输出 `query_string` |
| 新增路由（v1）    | `fta_web/alert/views.py`                     | `AlertViewSet.resource_routes` 增加 `generate_query_string` |
| 新增路由（v2）    | `fta_web/alert_v2/views.py`                  | `AlertV2ViewSet.resource_routes` 显式增加 `generate_query_string`，确保 `/alert/v2/` 可访问 |
| 参数定义对齐      | `fta_web/alert/serializers.py`（可选）       | 新增专用 Serializer（或在 Resource 内复用 `SearchConditionSerializer`） |
| 权限放行          | `fta_web/alert/views.py`                     | `check_permissions` 将 `generate_query_string` 与 `validate_query_string` 同级放行 |

---

## 0x02 接口协议

### a. 获取告警预设过滤条件

POST /apm/strategy/alert/builtin_filter/

#### 功能描述

获取 APM 应用/服务视角下的告警列表预设过滤条件，返回 Lucene query_string。

#### 请求参数

| 字段         | 类型         | 必选 | 描述                                                         |
| ------------ | ------------ | ---- | ------------------------------------------------------------ |
| bk_biz_id    | int          | 是   | 业务 ID                                                      |
| app_name     | string       | 是   | APM 应用名称                                                 |
| service_name | string       | 否   | APM 服务名称，传入时为服务视角，不传时为应用视角             |
| start_time   | int          | 否   | 开始时间（Unix 时间戳，秒），用于主机/容器关联查询           |
| end_time     | int          | 否   | 结束时间（Unix 时间戳，秒），用于主机/容器关联查询           |
| target_types | List[string] | 否   | 目标类型列表，可多选，仅服务视角需要传：<br />`APM-SERVICE`：本服务告警<br />`HOST`：关联主机告警<br />`K8S-WORKLOAD`：关联容器告警（K8S 工作负载） |

#### 请求示例

**应用视角**：

```json
{
    "bk_biz_id": 2,
    "app_name": "trpc-cluster-access-demo"
}
```

**服务视角**：

```json
{
    "bk_biz_id": 2,
    "app_name": "trpc-cluster-access-demo",
    "service_name": "bkm.web",
    "start_time": 1773371700,
    "end_time": 1773372600,
    "target_types": ["APM-SERVICE", "HOST", "K8S-WORKLOAD"]
}
```



#### 响应示例

**应用视角**：

```json
{
    "result": true,
    "code": 200,
    "message": "OK",
    "data": {
        "query_string": "target: trpc-cluster-access-demo\:* OR labels: \"APM-APP(trpc-cluster-access-demo)\""
    }
}
```

**服务视角**：

```json
{
    "result": true,
    "code": 200,
    "message": "OK",
    "data": {
        "query_string": "(target: \"trpc-cluster-access-demo:bkm.web\" OR labels: (\"APM-APP(trpc-cluster-access-demo)\" AND \"APM-SERVICE(bkm.web)\")) OR (target: (\"10.0.0.1|0\" OR \"10.0.0.2|0\")) OR (tags.bcs_cluster_id: \"BCS-K8S-00000\" AND tags.workload_kind: \"Deployment\" AND tags.workload_name: \"bkm-web\")"
    }
}
```

#### 影响接口

返回的 `query_string` 将作为预设过滤条件，注入以下告警中心接口的 `query_string` 参数：

| 接口           | 方法 | URL                                  |
| -------------- | ---- | ------------------------------------ |
| 查询告警       | POST | `fta/alert/v2/alert/search/`         |
| 导出告警       | POST | `fta/alert/v2/alert/export/`         |
| 告警分布直方图 | POST | `fta/alert/v2/alert/date_histogram/` |
| 告警标签       | POST | `fta/alert/v2/alert/tags/`           |
| 告警 TopN      | POST | `fta/alert/v2/alert/top_n/`          |

#### 使用说明：条件合并

前端嵌入告警中心页面时，将接口返回的 `query_string` 作为内置条件，与用户查询条件合并，用于查询或页面跳转条件回填。

假设内置条件为：

```text
target: "trpc-cluster-access-demo:bkm.web" OR labels: ("APM-APP(trpc-cluster-access-demo)" OR "APM-SERVICE(bkm.web)")
```

**场景 1：语句模式**

合并规则：`({内置 query_string}) AND ({用户查询条件})`

用户查询条件：

```text
labels: "haha"
```

合并结果：

```text
(target: "trpc-cluster-access-demo:bkm.web" OR labels: ("APM-APP(trpc-cluster-access-demo)" OR "APM-SERVICE(bkm.web)")) AND (labels: "haha")
```

**场景 2：UI  模式**

合并规则：

* 请求：用户条件（`conditions`）和内置条件（`query_string`）一并作为接口请求参数。
* 跳转：`({内置 query_string}) AND ({用户查询条件})`。

用户查询条件：

```json
{
    "conditions": [
        {
            "key": "labels",
            "method": "eq",
            "value": ["haha"]
        }
    ]
}
```

请求：

```json
{
    "conditions": [
        {
            "key": "labels",
            "method": "eq",
            "value": ["haha"]
        }
    ],
    "query_string": "target: \"trpc-cluster-access-demo:bkm.web\" OR labels: (\"APM-APP(trpc-cluster-access-demo)\" AND \"APM-SERVICE(bkm.web)\")"
}
```

跳转：

```text
(target: "trpc-cluster-access-demo:bkm.web" OR labels: ("APM-APP(trpc-cluster-access-demo)" OR "APM-SERVICE(bkm.web)")) AND (labels: "haha")
```



### b. 获取已关联策略数（FetchItemStatus 改造）

#### 功能描述

获取标签关联的策略数与告警数。

#### 请求参数

| 字段       | 类型         | 必选 | 描述                                         |
| ---------- | ------------ | ---- | -------------------------------------------- |
| bk_biz_id  | int          | 是   | 业务 ID                                      |
| metric_ids | List[string] | 否   | 指标 ID 列表，为空时基于 labels 返回策略汇总 |
| labels     | List[string] | 否   | 标签过滤列表                                 |

#### 请求示例

```json
{
    "bk_biz_id": 2,
    "metric_ids": [],
    "labels": ["APM-APP(trpc-cluster-access-demo)", "APM-SERVICE(bkm.web)"]
    // 应用视角
    // "labels": ["APM-APP(trpc-cluster-access-demo)"]
}
```

#### 响应示例

```json
{
    "result": true,
    "code": 200,
    "message": "OK",
    "data": {
        // 关联策略数
        "strategy_count": 12,
        // 未恢复告警数
        "alert_count": 3
    }
}
```

#### 使用说明：跳转策略列表

点击「已关联 N 个告警策略」跳转策略列表页时，仅按 `APM-SERVICE` 标签过滤：

```json
{
    "conditions": [
        {
            "key": "label_name",
            "value": ["/APM-SERVICE(bkm.web)/"]
        }
    ]
}
```

### c. conditions 转 query_string

POST `/alert/generate_query_string/`  
POST `/alert/v2/generate_query_string/`

#### 功能描述

将告警列表 UI 模式的 `conditions` 转换为 Lucene `query_string`，用于：

- APM 嵌入页内置条件与用户条件合并；
- 前端从 UI 模式切到语句模式时的条件回填。

#### 请求参数

| 字段       | 类型         | 必选 | 描述 |
| ---------- | ------------ | ---- | ---- |
| conditions | List[object] | 否   | 过滤条件列表，结构与 `AlertSearchSerializer.conditions` 一致，默认 `[]` |

`conditions[]` 子项：

| 字段      | 类型         | 必选 | 描述 |
| --------- | ------------ | ---- | ---- |
| key       | string       | 是   | 字段名 |
| value     | List[Any]    | 是   | 匹配值列表 |
| method    | string       | 是   | `eq` / `neq` / `include` / `exclude` / `gt` / `gte` / `lt` / `lte` |
| condition | string       | 否   | 与前一个条件的关系：`and` / `or` / `""`（默认 `""` 视为 `and`） |

#### 请求示例

```json
{
    "conditions": [
        {
            "key": "labels",
            "method": "eq",
            "value": ["APM-APP(trpc-cluster-access-demo)"],
            "condition": ""
        },
        {
            "key": "target",
            "method": "include",
            "value": ["bkm.web"],
            "condition": "and"
        },
        {
            "key": "severity",
            "method": "eq",
            "value": ["1"],
            "condition": "or"
        }
    ]
}
```

#### 响应示例

```json
{
    "result": true,
    "code": 200,
    "message": "OK",
    "data": "(labels: \"APM-APP(trpc-cluster-access-demo)\" AND target: *bkm.web*) OR severity: \"1\""
}
```

#### 组装规则

- 单条件内部复用 `QueryStringGenerator` 的值转义与操作符模板。
- 不做字段别名/展示名翻译，输入 `key` 需为统一字段名。
- 条件间按 `condition` 从左到右折叠，建议每个条件片段外层加括号以避免优先级歧义。
- 当 `conditions=[]` 时，返回空字符串 `""`。

---

## 0x03 参考

- `constants/alert.py`：`EventTargetType`、`K8STargetType`、`APMTargetType` 定义
- `constants/apm.py`：`ApmAlertHelper` 标签正则
- `apm_web/strategy/dispatch/builder.py`：策略 labels 构建
- `apm_web/handlers/host_handler.py`：`HostHandler.list_application_hosts`
- `apm_web/strategy/dispatch/entity.py`：`EntitySet.get_workloads`
- `monitor_web/strategies/resources/public.py`：`FetchItemStatus`
- `bkmonitor/utils/elasticsearch/handler.py`：`QueryStringGenerator`
- `monitor_web/data_explorer/event/resources.py`：`EventGenerateQueryStringResource`
- `apm_web/trace/resources.py`：`TraceGenerateQueryStringResource`
- `fta_web/alert/serializers.py`：`AlertSearchSerializer.conditions`
- `fta_web/alert/resources.py`：告警资源定义
- `fta_web/alert/views.py`：`AlertViewSet.resource_routes`
- `fta_web/alert_v2/views.py`：`AlertV2ViewSet.resource_routes`

---

*制定日期：2026-03-19*
