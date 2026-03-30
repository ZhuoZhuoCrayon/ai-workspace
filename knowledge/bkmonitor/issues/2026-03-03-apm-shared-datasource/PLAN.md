---
title: APM 跨应用共享数据源 —— 实施方案
tags: [apm, datasource, es, shared-storage, architecture]
issue: knowledge/bkmonitor/issues/2026-03-03-apm-shared-datasource/README.md
description: APM 跨应用共享数据源的实现方案与开发方案
created: 2026-03-03
updated: 2026-03-04
---

# APM 跨应用共享数据源 —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 实现方案

### a. 思路

**1）数据源复用**

**Before**：应用 <> 数据源 = 1 : 1，应用独占 RT → ES 索引线性膨胀。

**After**：应用 <> 数据源 = N : 1，多应用复用结果表 → 链路资源（例如索引、DataID）收敛。

**2）数据隔离**：补充 `bk_biz_id` 、`app_name`  到原始数据，并在路由、逻辑层分别进行业务、应用级别查询隔离。

### b. 模型设计

两条独立继承链：**共享数据源池**管理容量与元数据，**应用数据源**通过 `shared_datasource_id` 引用共享池。

```mermaid
classDiagram
    class BaseSharedDataSource {
        quota（容量）
        usage_count（用量）
        [元数据信息]
        allocate() · reserve() · activate() · release()
    }
    class SharedTraceDataSource {
    		[额外元数据信息]
    }
    class ApmDataSourceConfigBase {
        + shared_datasource_id
        set_from_shared()
        to_link_info()
    }
    class TraceDataSource {
        is_shared
    }

    BaseSharedDataSource <|-- SharedTraceDataSource
    ApmDataSourceConfigBase <|-- TraceDataSource
    TraceDataSource "N" --> "1" SharedTraceDataSource : shared_datasource_id
```

多应用复用同一共享数据源（N:1），共享池通过 quota / usage_count 控制容量，详细模型定义见 [0x02/a](#a-共享数据源模型)。

**关键决策**：

* **职责分离**：SharedDataSource 仅负责池管理（容量 + 元数据），不包含创建链路资源逻辑；链路资源创建由 `ApmDataSourceConfigBase` 的 `create_data_id` / `create_or_update_result_table` 以 `global_mode` 完成。
* **关联方式**：`shared_datasource_id` 为 IntegerField（可空，不建外键）；通过 `SHARED_DS_REGISTRY` 按 data_type 映射子类，便于扩展 Log/Metric。
* **Draft 模式**：reserve 创建草稿（`is_enabled=False`），外部 API 调用完成后由 activate 填充元数据并启用；allocate 仅选取 `is_enabled=True` 的实例，草稿不可见。

### c. 共享机制

**创建应用**：

数据源配置增加「是否共享数据源」参数，目前「空间类型」为 `bkapp` 的，默认设置为共享。

```mermaid
flowchart LR
    A[创建应用] --> B{共享?}
    B -->|是| C[<分配> 共享池]
    C -->|有可用| D[复制共享链路信息]
    C -->|无可用| E[创建]
    E --> F[<全局> 创建数据源]
    F --> G[<激活> 启用草稿]
    G --> D
    D --> H[保存]
    B -->|否| I[<独占> 创建数据源]
    I --> H
```

**迁出**：从共享模式切换为独占模式。

```mermaid
flowchart LR
    A[apply_datasource] --> B{"变更为独占？"}
    B -->|是| C[释放共享池]
    C --> D[<独占> 创建数据源]
```

### d. 命名规则


| 项                   | 独占模式                                 | 共享模式                                |
| ------------------- | ------------------------------------ | ----------------------------------- |
| **bk_biz_id**       | 实际业务 ID                              | 0（全局注册）                             |
| **data_name**       | `{bk_biz_id}_bkapm_trace_{app_name}` | `bkapm_shared_trace_{seq:04d}`      |
| **result_table_id** | `{bk_biz_id}_bkapm.trace_{app_name}` | `apm_global.shared_trace_{seq:04d}` |

> `seq` ：共享数据源表主键（AUTO_INCREMENT），每个子类独立编号。
>
> `data_name` ：property 推导，不单独存储。

### e. 数据链路

**写入**：bk-collector 从 Token 反解 `bk_biz_id` 、 `app_name`，注入到原始数据。

**查询**：

* 逻辑层（应用级别隔离）：所有查询路径统一追加 `bk_biz_id` + `app_name` 过滤条件。
* 路由层（业务级别隔离）：支持以 `bk_biz_id` 作为 filter 查询业务 0 的全局结果表。

### f. 风险与约束


| 风险                 | 应对                                                         |
| -------------------- | ------------------------------------------------------------ |
| 共享索引故障爆炸半径 | quota 合理设定 + 监控                                        |
| 已删除应用数据残留   | ES ILM 自然过期                                              |

---

## 0x02 开发方案

### a. 共享数据源模型

`apm/models/datasource.py`

#### 模型概览

两条继承链：共享数据源池（BaseSharedDataSource）管理容量与元数据；应用数据源（ApmDataSourceConfigBase）通过 `shared_datasource_id` 引用共享池。完整类图如下：

```mermaid
classDiagram
    class BaseSharedDataSource {
        <<abstract>>
        int quota
        int usage_count
        str data_type
        bool is_enabled
        int bk_data_id
        str result_table_id
        allocate(data_type) dict | None
        reserve(data_type) Self
        activate(link_info)
        release()
        to_shared_info() dict*
        data_name* property
    }
    class SharedTraceDataSource {
        int index_set_id
        str index_set_name
        to_shared_info() dict
    }
    class ApmDataSourceConfigBase {
        <<abstract>>
        int bk_biz_id
        str app_name
        int bk_data_id
        str result_table_id
        int shared_datasource_id
        apply_datasource()
        set_from_shared(info_dict)
        to_link_info() dict
        start()
        stop()
        create_data_id(global_mode)
        create_or_update_result_table(global_mode)
    }
    class TraceDataSource {
        bool is_shared
        set_from_shared(info_dict)
        to_link_info() dict
        _shared_filter_params()
    }
    BaseSharedDataSource <|-- SharedTraceDataSource
    ApmDataSourceConfigBase <|-- TraceDataSource
    TraceDataSource "*" --> "1" SharedTraceDataSource : shared_datasource_id
```



#### 核心流程

**allocate**：选取可用共享源并占用，无可用时返回 None。

```mermaid
flowchart LR
    A[开启事务] --> B[可用实例选择]
    B --> C{存在可用实例?}
    C -->|否| D[返回 None]
    C -->|是| E[usage + 1]
    E --> F[返回 to_shared_info]
```

💡 Tips：

* 并发保护：`select_for_update()`。
* 可用实例选择：`filter(usage_count__lt=F('quota'), is_enabled=True)`。
* 负载均衡：`order_by('usage_count')`。
* 原子保证：`update(usage_count=F('usage_count') + 1)`。

**reserve**：创建草稿实例（`is_enabled=False`），pk 即 seq，用于推导 `data_name` / `result_table_id`。

```mermaid
flowchart LR
    A[创建草稿记录] --> B[共享数据源 pk]
    B --> C["bkapm_shared_trace_{pk:04d}"]
```

💡 Tips： DB 默认值使用草稿状态：`is_enabled=False, usage_count=0`

**activate**：外部 API 调用成功后，填充链路元数据并启用。

```mermaid
flowchart LR
    A["接收 link_info（来自 DataSource.to_link_info）"] --> B[填充]
    B --> C["usage_count=1, is_enabled=True"]
    C --> D[save]
```

💡 Tips：

* 设置链路信息：从 `link_info` dict 填充 `bk_data_id`、`result_table_id` 及子类扩展字段。
* 启用：`usage_count=1, is_enabled=True`。

**release**：释放占用，usage_count 减 1。

💡 Tips：`Greatest(F('usage_count') - 1, 0)` 防止 usage_count 变为负数。


#### SharedTraceDataSource

继承 BaseSharedDataSource，新增以下扩展字段：


| 字段             | 类型           | 说明         |
| -------------- | ------------ | ---------- |
| index_set_id   | IntegerField | 索引集 ID（可选） |
| index_set_name | CharField    | 索引集名称（可选）  |

 `to_shared_info()`：在基类返回的字典基础上追加上述扩展字段。

该字典由 `TraceDataSource.set_from_shared()` 消费。`to_shared_info()` 与 `to_link_info()` 的字段集相同（bk_data_id、result_table_id、index_set_id 等），方向相反：前者从 SharedDS 导出，后者从 DataSource 导出。

#### 注册表

data_type → SharedDataSource 子类映射，供 apply_datasource 按类型查找并调用 allocate/reserve：

```python
SHARED_DS_REGISTRY = {
    "trace": SharedTraceDataSource,
    # "log": SharedLogDataSource,  # future
}
```

### b. ApmDataSourceConfigBase 变更

`apm/models/datasource.py`


| 变更点                                       | 目标                                                         |
| -------------------------------------------- | ------------------------------------------------------------ |
| **[Field]** `shared_datasource_id`           | 新增字段。                                                   |
| **[Method]** `apply_datasource`              | 增加共享数据源处理逻辑（见下方流程）。                       |
| **[Method]** `create_data_id`                | 增加 `global_mode` 、`data_name[可选]` 参数。                |
| **[Method]** `create_or_update_result_table` | 增加 `global_mode` `result_table_id[可选]` 参数。            |
| **[Method]** `to_link_info`                  | 导出链路元数据字典（bk_data_id、result_table_id 等），子类覆写追加特有字段。 |
| **[Method]**  `set_from_shared`              | 由子类覆写，从共享链路信息字典提取各自字段并赋值。           |
| **[Method]** `is_shared`                     | 是否共享，通过 `shared_datasource_id` 判断。                 |
| **[Method]** `start / stop`                  | 共享模式下不执行。                                           |

**apply_datasource 共享数据源处理流程**（详见 [0x01/c 共享机制](#c-共享机制) 流程图）：

```mermaid
flowchart TD
    A([apply_datasource]) --> M{迁出？}

    M -->|是| N[<释放> 共享源]
    N --> O[<重置> 数据源信息]
    O --> K[<独占> create_data_id]

    M -->|否| B{共享?}

    B -->|是| C[<分配> allocate]
    C -->|有可用| D[set_from_shared]
    C -->|无可用| E[<草稿> reserve]
    E --> F[<全局> create_data_id]
    F --> G[<全局> create_or_update_result_table]
    G --> H[<激活> reserved.activate]
    H --> I[<激活> shared_datasource_id ← pk]
    I --> D

    B -->|否| K
    K --> Q[<独占> create_or_update_result_table]

    D --> J([save])
    Q --> J

    classDef migrate fill:#5d4037,stroke:#ffab91,color:#ffccbc
    classDef shared fill:#1b5e20,stroke:#81c784,color:#c8e6c9
    classDef dedicated fill:#0d47a1,stroke:#64b5f6,color:#bbdefb

    class N,O migrate
    class C,D,E,F,G,H,I shared
    class K,Q dedicated
```

> API 失败回滚：`create_data_id` 或 `create_or_update_result_table` 抛异常时，删除草稿（`reserved.delete()`）并向上传播。
>
> 迁出：`release()` 释放共享源占用后，清空 `shared_datasource_id` 及共享链路字段，随后进入独占创建流程。



### c. TraceDataSource 查询适配

`apm/models/datasource.py`


| 变更点                       | 说明                                  |
| ---------------------------- | ------------------------------------- |
| `build_filter_params`        | 增加过滤 <`bk_biz_id` / `app_name`>。 |
| `update_or_create_index_set` | 共享模式下不创建日志索引集。          |


### d. 应用生命周期

**创建**（`apm/resources.py` — `CreateApplicationResource` / `ApplyDatasourceResource`）：

```mermaid
flowchart LR
    A[API] --> B[param: shared_datasource_types]
    B --> C[`xx_datasource_option.is_shared`]
    C --> D[perform_request]
    D --> E["apply_datasource<option>"]
```

| 变更点                                | 说明                                                         |
| ------------------------------------- | ------------------------------------------------------------ |
| **[Field]** `shared_datasource_types` | 新增字段： `CreateApplicationResource` / `ApplyDatasourceResource`。<br />默认值：`space_type` 为 `bkapp` 时，使用 `["trace"]`。<br /><br />操作：设置到 `xx_datasource_option.is_shared`。 |



**删除**（`apm/task/tasks.py` — `delete_application_async`，由 `DeleteApplicationResource` 触发）：

```mermaid
flowchart LR
    A[DeleteApplicationResource] --> B[delete_application_async]
    B --> C[stop_trace]
    C --> D[stop]
    D --> E{is_shared?}
    E -->|是| F["release(only)"]
    E -->|否| G["stop"]
```

- 共享模式：调用 `release()` 并不执行 stop 原流程。

### e. 应用信息注入


| 变更点                   | 说明                                                         |
| ------------------------ | ------------------------------------------------------------ |
| 清洗阶段（bk-collector） | 注入 `bk_biz_id` 、 `app_name` 到 Span（Token 反解），和 `resource` 同一级，无论共享与否均注入。 |
| 应用创建阶段（SaaS）     | 增加 `bk_biz_id` 、 `app_name` 作为 ES mapping 字段。       |

### f. 查询路径审计

增加 <`bk_biz_id`、`app_name`> 过滤。


| 路径                             | 方式               |
| -------------------------------- | ------------------ |
| `TraceDataSource.get_q`          | QueryConfigBuilder |
| `BaseQuery._get_q` → SpanQuery   | QueryConfigBuilder |
| `TopoHandler.list_trace_ids`     | 直接 ES DSL        |
| `apm_web/meta/resources.py`      | QueryConfigBuilder |
| `monitor_web/overview/search.py` | QueryConfigBuilder |
| `apm_web/handlers/db_handler.py` | QueryConfigBuilder |


> 上线前需对代码库执行 `rg "QueryConfigBuilder.*BK_APM"` 和 `rg "es_client\.search"` 全量检索，确认所有查询路径已适配。

---

*制定日期：2026-03-03*
