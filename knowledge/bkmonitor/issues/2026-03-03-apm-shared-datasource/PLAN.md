---

## title: APM 跨应用共享数据源 —— 实施方案
tags: [apm, datasource, es, shared-storage, architecture]
issue: knowledge/bkmonitor/issues/2026-03-03-apm-shared-datasource/README.md
description: APM 跨应用共享数据源的实现方案与开发方案
created: 2026-03-03
updated: 2026-03-03
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
        allocate() · register() · release()
    }
    class SharedTraceDataSource {
    		[额外元数据信息]
    }
    class ApmDataSourceConfigBase {
        + shared_datasource_id
        set_from_shared()
    }
    class TraceDataSource

    BaseSharedDataSource <|-- SharedTraceDataSource
    ApmDataSourceConfigBase <|-- TraceDataSource
    SharedTraceDataSource "1" <-- "*" TraceDataSource : shared_datasource_id
```



多应用复用同一共享数据源（N:1），共享池通过 quota / usage_count 控制容量，详细模型定义见 [0x02/a](#a-共享数据源模型)。

**关键决策**：

* **职责分离**：SharedDataSource 仅负责池管理（容量 + 元数据），不包含创建链路资源逻辑。
* **关联方式**：`shared_datasource_id` 为 IntegerField（可空，不建外键）；通过 `SHARED_DS_REGISTRY` 按 data_type 映射子类，便于扩展 Log/Metric。
* **事务与并发**：allocate 使用 `select_for_update` 保证选取原子性；创建在事务外执行（避免长事务持有外部 API 调用）；register 通过 unique 约束防止并发重复注册。

### c. 共享机制

**创建应用**：

```mermaid
flowchart LR
    A[创建应用] --> B{使用共享数据源?}
    B -->|是| C[从共享池分配]
    C -->|有可用| D[复制共享链路信息]
    C -->|无可用| E[以全局模式创建数据链路]
    E --> F[注册到共享池]
    F --> D
    D --> H[保存]
    B -->|否| G[独占模式：创建专属数据链路]
    G --> H
```

### d. 命名规则


| 项                   | 独占模式                                 | 共享模式                                |
| ------------------- | ------------------------------------ | ----------------------------------- |
| **bk_biz_id**       | 实际业务 ID                              | 0（全局注册）                             |
| **data_name**       | `{bk_biz_id}_bkapm_trace_{app_name}` | `bkapm_shared_trace_{seq:04d}`      |
| **result_table_id** | `{bk_biz_id}_bkapm.trace_{app_name}` | `apm_global.shared_trace_{seq:04d}` |


> **bk_biz_id 双重语义**：metadata 注册 bk_biz_id=0（全局结果表），ES 文档中 bk_biz_id 字段为实际业务 ID。

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
| 并发 allocate 竞态   | allocate 内 `select_for_update`；register 用 unique 约束防止重复注册，冲突时回滚并重新调用 allocate |

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
        ---
        int bk_data_id
        str result_table_id
        ---
        allocate(data_type) dict | None
        register(data_type, info_dict) Self
        release()
        to_shared_info() dict*
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
        ---
        apply_datasource()
        set_from_shared(info_dict)
        start()
        stop()
        create_data_id(global_mode)
        create_or_update_result_table(global_mode)
    }
    class TraceDataSource {
        bool is_shared
        set_from_shared(info_dict)
        _shared_filter_params()
    }
    BaseSharedDataSource <|-- SharedTraceDataSource
    ApmDataSourceConfigBase <|-- TraceDataSource
    SharedTraceDataSource "1" <-- "*" TraceDataSource : shared_datasource_id
```



#### 核心流程

**allocate**：选取可用共享源并占用，无可用时返回 None。

```mermaid
flowchart LR
    A[开启事务] --> B[行级锁选取最空闲的可用共享源]
    B --> C{存在可用实例?}
    C -->|否| D[返回 None]
    C -->|是| E[原子自增 usage_count]
    E --> F[返回 to_shared_info]
```

**register**：将新建的数据链路注册为共享源，usage_count 初始为 1。

```mermaid
flowchart LR
    A[开启事务] --> B[创建 SharedDataSource 记录] --> C[返回 to_shared_info]
```

> 并发新建：对 `(data_type, bk_data_id)` 添加 unique 约束。冲突时捕获 IntegrityError，回滚并重新调用 allocate。

**release**：释放占用，usage_count 减 1。

```mermaid
flowchart LR
    A[原子递减 usage_count] --> B[完成]
```



#### ORM 实现提示


| 方法           | 关键技巧                                                                                                                                                                       |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **allocate** | `select_for_update()` 行锁防止并发竞态；`filter(usage_count__lt=F('quota'), is_enabled=True)` 只选可用实例；`order_by('usage_count')` 负载均衡；`update(usage_count=F('usage_count') + 1)` 原子自增 |
| **register** | unique 约束 `(data_type, bk_data_id)` 防止并发重复注册；冲突时捕获 `IntegrityError`，回滚后重新 allocate                                                                                         |
| **release**  | `Greatest(F('usage_count') - 1, 0)` 防止 usage_count 变为负数                                                                                                                    |


#### SharedTraceDataSource

继承 BaseSharedDataSource，新增以下扩展字段：


| 字段             | 类型           | 说明         |
| -------------- | ------------ | ---------- |
| index_set_id   | IntegerField | 索引集 ID（可选） |
| index_set_name | CharField    | 索引集名称（可选）  |


覆写 `to_shared_info()`，在基类返回的字典基础上追加上述扩展字段。该字典由 `TraceDataSource.set_from_shared()` 消费。

#### 注册表

data_type → SharedDataSource 子类映射，供 apply_datasource 按类型查找并调用 allocate/register：

```python
SHARED_DS_REGISTRY = {
    "trace": SharedTraceDataSource,
    # "log": SharedLogDataSource,  # future
}
```

### b. ApmDataSourceConfigBase 变更

`apm/models/datasource.py`


| 变更点                           | 当前                                             | 目标                                               |
| ----------------------------- | ---------------------------------------------- | ------------------------------------------------ |
| 模型                            | —                                              | 新增 shared_datasource_id: IntegerField(null=True) |
| apply_datasource              | create_data_id → create_or_update_result_table | 增加共享数据源处理逻辑（见下方流程）                               |
| create_data_id                | 以业务 bk_biz_id 创建                               | 增加 global_mode 参数：True 时 bk_biz_id=0、全局命名        |
| create_or_update_result_table | 以业务维度创建                                        | 增加 global_mode 参数：True 时使用全局 table_id，不创建索引集     |
| start / stop                  | switch_result_table                            | 共享模式下不执行                                         |


新增 property：`is_shared -> bool`（`return self.shared_datasource_id is not None`）

新增方法：`set_from_shared(info_dict)`，由子类覆写，从共享链路信息字典提取各自字段并赋值。

**apply_datasource 共享数据源处理流程**（详见 [0x01/e 应用生命周期](#e-应用生命周期) 流程图）：

```mermaid
flowchart TD
    A[apply_datasource] --> B{共享?}
    B -->|是| C["SHARED_DS_REGISTRY[data_type].allocate()"]
    C -->|有可用| D["set_from_shared(shared_info)"]
    C -->|无可用| E["create_data_id(global_mode=True)"]
    E --> F["create_or_update_result_table(global_mode=True)"]
    F --> G["SharedDS.register()"]
    G -->|成功| H["shared_datasource_id = registered.id"]
    G -.->|IntegrityError| I["回滚 → 重新 allocate"]
    I --> D
    H --> D
    D --> J[save]
    B -->|否| K["原有流程：create_data_id → create_or_update_result_table"]
    K --> J
```



### c. TraceDataSource 查询适配

`apm/models/datasource.py`


| 变更点                          | 说明                                                         |
| ---------------------------- | ---------------------------------------------------------- |
| 新增 `_shared_filter_params()` | 共享时返回 `[{bk_biz_id filter}, {app_name filter}]`，非共享返回 `[]` |
| `build_filter_params`        | 合并 `_shared_filter_params()`                               |
| `update_or_create_index_set` | 共享模式下不执行                                                   |
| `stop`                       | 共享模式下不执行索引集删除                                              |


### d. 应用生命周期

**创建**（`apm/resources.py` — `CreateApplicationResource`）：

```mermaid
flowchart LR
    A[API 请求] --> B[RequestSerializer 解析 shared_datasource_types]
    B --> C[perform_request]
    C --> D["apply_datasource（按类型执行共享数据源流程）"]
```

- `RequestSerializer` 新增 `shared_datasource_types` 参数（如 `["trace"]`），或根据 `space_type` 自动推断
- `perform_request` 将共享类型列表传入 `apply_datasource`，按类型执行共享数据源流程

**删除**（`apm/task/tasks.py` — `delete_application_async`，由 `DeleteApplicationResource` 触发）：

```mermaid
flowchart LR
    A[DeleteApplicationResource] --> B[delete_application_async]
    B --> C[stop_trace]
    C --> D{is_shared?}
    D -->|是| E["release() + 不执行 stop"]
    D -->|否| F[原有 stop 流程]
```

- `stop_trace` 前检查 `is_shared`：共享模式下调用 `release()` 并不执行 stop 流程
- 非共享模式执行原有 stop 流程

### e. bk-collector


| 变更点   | 说明                                                         |
| -------- | ------------------------------------------------------------ |
| 清洗阶段 | 注入 `bk_biz_id` 、 `app_name` 到 Span（Token 反解），和 `resource` 同一级，无论共享与否均注入。 |


### f. 查询路径审计


| #    | 路径                             | 方式               | 适配                                  |
| ---- | -------------------------------- | ------------------ | ------------------------------------- |
| 1    | `TraceDataSource.get_q`          | QueryConfigBuilder | `build_filter_params` 合并 → 自动生效 |
| 2    | `BaseQuery._get_q` → SpanQuery   | QueryConfigBuilder | --                                    |
| 3    | `TopoHandler.list_trace_ids`     | 直接 ES DSL        | `query.bool.must` 追加 term filter    |
| 4    | `apm_web/meta/resources.py`      | QueryConfigBuilder | 追加 filter                           |
| 5    | `monitor_web/overview/search.py` | QueryConfigBuilder | 追加 filter                           |
| 6    | `apm_web/handlers/db_handler.py` | QueryConfigBuilder | 追加 filter                           |


> 上线前需对代码库执行 `rg "QueryConfigBuilder.*BK_APM"` 和 `rg "es_client\.search"` 全量检索，确认所有查询路径已适配。

---

*制定日期：2026-03-03*