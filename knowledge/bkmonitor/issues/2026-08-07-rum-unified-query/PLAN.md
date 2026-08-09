---
title: RUM 分层统一查询 —— 实施方案
tags: [rum, query, span, view, session, factory, unify-query]
issue: ./README.md
description: 通过 Level 工厂统一 Span、View、Session 的查询类与 Resource 接口
created: 2026-08-07
updated: 2026-08-09
---

# RUM 分层统一查询 —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 方案结论

### a. 目标调用链

RUM 只保留一组查询接口：

- `mode` 选择 Level。
- Factory、Level、Query 共用同一份 `list[TraceDatasourceTarget]`。

```text
Resource
  └── RumLevelHandlerFactory.create(mode, data_sources)
        └── Span / View / Session LevelHandler(data_sources)
              ├── self.query → Span / View / Session Query → BaseQuery
              └── self.span_query → SpanQuery → BaseQuery（可选兜底）
```

| 决策点 | 结论 |
| --- | --- |
| HTTP 入口 | Resource 自行实现 `perform_request()`，不设公共基类 |
| Level 分派 | `RumLevelHandlerFactory` 只维护 `mode → LevelHandler` 映射 |
| 初始化参数 | Factory、Level、Query 均接收 `list[TraceDatasourceTarget]` |
| 结果表承载 | `table_id` 存原始表，`levels` 存层级结果表 |
| 查询职责 | Query 提供原子查询，Level 组合一个或多个 Query |

### b. 方案边界

本方案确定类关系、代码位置、Level 方法、Resource 路由和调用方式。以下内容不在范围内：

- 请求字段、响应字段和错误码。
- View、Session 的预计算链路与数据生产方式。
- View、Session 查询原子的具体实现。
- 各 Level 页面配置和查询参数的业务细节。

## 0x02 架构设计

### a. 总体结构

```mermaid
flowchart LR
    Client["RUM 调用方"] --> Resource["独立 Resource<br/>9 个统一入口"]
    Resource -- "mode + data_sources" --> Factory["RumLevelHandlerFactory"]

    Factory -- "span" --> SpanLevel["SpanLevelHandler"]
    Factory -- "view" --> ViewLevel["ViewLevelHandler"]
    Factory -- "session" --> SessionLevel["SessionLevelHandler"]

    SpanLevel --> SpanQuery["SpanQuery"]
    ViewLevel --> ViewQuery["ViewQuery"]
    ViewLevel -. "Span 兜底" .-> SpanQuery
    SessionLevel --> SessionQuery["SessionQuery"]
    SessionLevel -. "Span 兜底" .-> SpanQuery

    SpanQuery --> BaseQuery["BaseQuery<br/>存储查询原语"]
    ViewQuery --> BaseQuery
    SessionQuery --> BaseQuery
    BaseQuery --> UQ["UnifyQuery"]

    Target["list[TraceDatasourceTarget]<br/>table_id · app · levels"] -. "Resource 构造" .-> Resource

    classDef api fill:#FFF4E5,stroke:#C77700,color:#333;
    classDef level fill:#E8F3FF,stroke:#3A84FF,color:#333;
    classDef query fill:#EAF7EE,stroke:#3E9B59,color:#333;
    classDef target fill:#F2EDFF,stroke:#8064D6,color:#333;

    class Resource,Factory api;
    class SpanLevel,ViewLevel,SessionLevel level;
    class SpanQuery,ViewQuery,SessionQuery,BaseQuery query;
    class Target target;
```

| 层 | 负责 | 不负责 |
| --- | --- | --- |
| Resource | 权限、参数校验、构造 `data_sources`、调用 Level | 选择具体 Level 类或执行存储查询 |
| Factory | 校验 `mode`、构造对应 Level | 解析结果表或实现接口能力 |
| Level | 组合一个或多个 Query，组装接口能力 | 处理 HTTP 或直接访问 UnifyQuery |
| Query | 从 Target 选择层级表、构造并执行存储查询 | 页面配置和 HTTP 返回组装 |

### b. 数据源目标

代码位置：`bkmonitor/data_source/utils/apm.py`。

```python
@dataclass(frozen=True)
class LevelTarget:
    name: str
    table_ids: list[str]


@dataclass(frozen=True)
class TraceDatasourceTarget:
    table_id: str
    app: APMAppTarget
    levels: list[LevelTarget] = field(default_factory=list)
```

```mermaid
classDiagram
    class TraceDatasourceTarget {
        +str table_id
        +APMAppTarget app
        +list~LevelTarget~ levels
    }
    class LevelTarget {
        +str name
        +list~str~ table_ids
    }
    TraceDatasourceTarget "1" o-- "0..*" LevelTarget : levels
```

| 查询层级 | 结果表来源 |
| --- | --- |
| Span | `TraceDatasourceTarget.table_id` |
| View | `TraceDatasourceTarget.levels` 中 `name = "view"` 的 `table_ids` |
| Session | `TraceDatasourceTarget.levels` 中 `name = "session"` 的 `table_ids` |

目标模型遵循以下约束：

- `table_id` 仍表示原始表。
- `levels` 默认为空，兼容现有 `TraceDatasourceTarget.build()` 和 APM 调用方。
- `LevelTarget.name` 是通用结果表标识，不绑定 RUM 的 `mode`。
- `levels` 也可承接 `trace` 等其他预计算结果表。

## 0x03 开发方案

### a. 代码落点

```text
bkmonitor/data_source/utils/
├── query.py                                  # [Keep] BaseQuery
└── apm.py                                    # [Change] LevelTarget、TraceDatasourceTarget.levels

packages/rum_web/
├── constants.py                              # [Change] RumQueryMode
├── query/
│   ├── resources.py                          # [Add] 9 个独立 Resource
│   ├── views.py                              # [Add] SearchViewSet
│   └── urls.py                               # [Add] ResourceRouter，生成 search/
├── urls.py                                   # [Change] 在根路径挂载 rum_web.query.urls
└── handlers/
    ├── query/
    │   ├── span.py                           # [Change] SpanQuery
    │   ├── view.py                           # [Reserved] ViewQuery
    │   └── session.py                        # [Reserved] SessionQuery
    └── level/
        ├── base.py                           # [Add] BaseRumLevelHandler
        ├── factory.py                        # [Add] RumLevelHandlerFactory
        ├── span.py                           # [Add] SpanLevelHandler
        ├── view.py                           # [Reserved] ViewLevelHandler
        └── session.py                        # [Reserved] SessionLevelHandler
```

View、Session 文件只固定类名与扩展位置，其查询实现不属于本方案。

### b. `mode` 与 Factory

Factory 只接受 `span`、`view`、`session`。首期只注册 `span`。View、Session 就绪后再注册。

```python
class RumQueryMode:
    SPAN = "span"
    VIEW = "view"
    SESSION = "session"


class RumLevelHandlerFactory:
    HANDLERS = {
        RumQueryMode.SPAN: SpanLevelHandler,
    }

    @classmethod
    def create(
        cls,
        mode: str,
        data_sources: list[TraceDatasourceTarget],
    ) -> BaseRumLevelHandler:
        if mode not in cls.HANDLERS:
            raise UnsupportedRumQueryMode(mode)
        return cls.HANDLERS[mode](data_sources)
```

Factory 只负责模式校验和 Level 实例化。

### c. 基础查询层

| 类               | 代码位置                                         | 状态   |
| --------------- | -------------------------------------------- | ---- |
| `BaseQuery`     | `bkmonitor/data_source/utils/query.py`       | 保留   |
| `SpanQuery`     | `packages/rum_web/handlers/query/span.py`    | 补齐   |
| `ViewQuery`     | `packages/rum_web/handlers/query/view.py`    | 后续新增 |
| `SessionQuery`  | `packages/rum_web/handlers/query/session.py` | 后续新增 |

`BaseQuery` 是基础查询层唯一的公共抽象。三个 Query 均接收 `data_sources: list[TraceDatasourceTarget]`。

基础查询层提供以下原子能力：

```text
query_list
query_total
query_field_topk
query_option_values
query_graph_config
query_field_aggregated_value
query_detail
```

### d. Level 与 Query 交互

`BaseRumLevelHandler.__init__()` 只保存 `data_sources`，不创建 Query。

具体 Level 按业务需要组合 Query。

```mermaid
classDiagram
    class BaseRumLevelHandler {
        <<abstract>>
        +list~TraceDatasourceTarget~ data_sources
        +__init__(data_sources)
    }
    class SpanLevelHandler
    class ViewLevelHandler
    class SessionLevelHandler
    class BaseQuery
    class SpanQuery
    class ViewQuery
    class SessionQuery

    BaseRumLevelHandler <|-- SpanLevelHandler
    BaseRumLevelHandler <|-- ViewLevelHandler
    BaseRumLevelHandler <|-- SessionLevelHandler

    BaseQuery <|-- SpanQuery
    BaseQuery <|-- ViewQuery
    BaseQuery <|-- SessionQuery

    SpanLevelHandler --> SpanQuery : query
    ViewLevelHandler --> ViewQuery : query
    ViewLevelHandler --> SpanQuery : span_query
    SessionLevelHandler --> SessionQuery : query
    SessionLevelHandler ..> SpanQuery : optional span_query
```

```python
from abc import ABC, abstractmethod
from typing import Any

from bkmonitor.data_source.utils import types


class BaseRumLevelHandler(ABC):
    def __init__(self, data_sources: list[TraceDatasourceTarget]):
        self.data_sources = data_sources

    @abstractmethod
    def view_config(
        self,
        extra_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...

    @abstractmethod
    def generate_query_string(
        self,
        filters: list[types.Filter],
        extra_config: dict[str, Any] | None = None,
    ) -> str:
        ...

    @abstractmethod
    def field_topk(
        self,
        start_time: int,
        end_time: int,
        field: str,
        limit: int = 5,
        filters: list[types.Filter] | None = None,
        query_string: str = "",
        extra_config: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def field_statistics_info(
        self,
        start_time: int,
        end_time: int,
        field: dict[str, Any],
        filters: list[types.Filter] | None = None,
        query_string: str = "",
        extra_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...

    @abstractmethod
    def field_statistics_graph(
        self,
        start_time: int,
        end_time: int,
        field: dict[str, Any],
        filters: list[types.Filter] | None = None,
        query_string: str = "",
        extra_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...

    @abstractmethod
    def download_topk(
        self,
        start_time: int,
        end_time: int,
        field: str,
        limit: int = 5,
        filters: list[types.Filter] | None = None,
        query_string: str = "",
        extra_config: dict[str, Any] | None = None,
    ) -> bytes:
        ...

    @abstractmethod
    def get_fields_option_values(
        self,
        start_time: int,
        end_time: int,
        fields: list[str],
        limit: int = 10,
        filters: list[types.Filter] | None = None,
        query_string: str = "",
        extra_config: dict[str, Any] | None = None,
    ) -> dict[str, list[str]]:
        ...

    @abstractmethod
    def list_records(
        self,
        start_time: int,
        end_time: int,
        offset: int = 0,
        limit: int = 10,
        filters: list[types.Filter] | None = None,
        query_string: str = "",
        sort: list[str] | None = None,
        extra_config: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def record_detail(
        self,
        record_id: str,
        extra_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...


class ViewLevelHandler(BaseRumLevelHandler):
    def __init__(self, data_sources: list[TraceDatasourceTarget]):
        super().__init__(data_sources)
        self.query = ViewQuery(data_sources)
        self.span_query = SpanQuery(data_sources)
```

`extra_config` 的边界：

- 具体 Level 按白名单解析。
- 不得覆盖显式参数或 `data_sources`。
- 不得整包传给 Query。

### e. Resource 与 Level 交互

以 `RumFieldTopKResource` 为例：

```python
class RumFieldTopKResource(Resource):
    RequestSerializer = RumFieldTopKRequestSerializer

    def perform_request(self, data):
        mode = data.pop("mode")
        application = self.get_authorized_application(data)
        data_sources = [
            TraceDatasourceTarget.build(
                bk_biz_id=application.bk_biz_id,
                app_name=application.app_name,
                table_id=application.span_result_table_id,
            )
        ]

        handler = RumLevelHandlerFactory.create(mode, data_sources)
        return handler.field_topk(
            start_time=data["start_time"],
            end_time=data["end_time"],
            field=data["field"],
            limit=data["limit"],
            filters=data["filters"],
            query_string=data["query_string"],
            extra_config=data.get("extra_config"),
        )
```

- `data_sources` 只从授权后的 `Application` 构造，客户端不能指定结果表。
- View、Session 接入后，也在此处补入 `levels`。
- Resource 只校验 `extra_config` 是对象；配置项由具体 Level 校验。

### f. Resource 接口

路由命名：

```text
/rum/                       # 项目根路由
  └── search/                # SearchViewSet
      └── {API}/              # Resource action
```

`query` 是内部模块名；`search` 是对外路径。`rum_web.urls` 在根路径挂载 `rum_web.query.urls`。

| HTTP | URL                                       | Resource                          | Level 方法                   |
| ---- | ----------------------------------------- | --------------------------------- | ---------------------------- |
| GET  | `/rum/search/view_config/`                | `RumViewConfigResource`           | `view_config`                |
| POST | `/rum/search/generate_query_string/`      | `RumGenerateQueryStringResource`  | `generate_query_string`      |
| POST | `/rum/search/field_topk/`                 | `RumFieldTopKResource`            | `field_topk`                 |
| POST | `/rum/search/field_statistics_info/`      | `RumFieldStatisticsInfoResource`  | `field_statistics_info`      |
| POST | `/rum/search/field_statistics_graph/`     | `RumFieldStatisticsGraphResource` | `field_statistics_graph`     |
| POST | `/rum/search/download_topk/`              | `RumDownloadTopKResource`         | `download_topk`              |
| POST | `/rum/search/get_fields_option_values/`   | `RumFieldsOptionValuesResource`   | `get_fields_option_values`   |
| POST | `/rum/search/list_records/`               | `RumRecordsResource`              | `list_records`               |
| POST | `/rum/search/record_detail/`              | `RumRecordDetailResource`         | `record_detail`              |

## 0x04 验收与验证

新增测试位于 `packages/rum_web/tests/query/`：

| 测试 | 核心断言 |
| --- | --- |
| `test_datasource_target.py` | [a] `levels` 默认空列表<br />[b] 现有 `TraceDatasourceTarget.build()` 行为不变<br />[c] 可携带多个层级结果表 |
| `test_level_factory.py` | [a] 合法 `mode` 返回对应 Level<br />[b] 未注册模式明确失败<br />[c] `data_sources` 原样传入 Level |
| `test_query.py` | [a] 已实现 Query 复用 `BaseQuery`<br />[b] 接收 `list[TraceDatasourceTarget]`<br />[c] 具备 7 项原子能力 |
| `test_level_handler.py` | [a] 基类只保存 `data_sources`<br />[b] 具体 Level 可组合多个 Query<br />[c] TopK 方法只接收单个字段<br />[d] 9 项公共方法声明参数与返回类型<br />[e] 未知配置被拒绝，且不能覆盖公共参数或数据源 |
| `test_query_resources.py` | [a] 9 个 URL、HTTP 方法、Resource 和 Level 方法一一对应<br />[b] Resource 不依赖公共基类<br />[c] `extra_config` 与公共参数独立传入 Level |

测试门禁：

```bash
pytest packages/rum_web/tests/query -q
```

静态依赖同时确认：

- `packages/rum_web/handlers/query/` 不导入 DRF、Resource 或页面模块。
- Factory 不读取 `TraceDatasourceTarget.table_id` 或 `levels`。
- 客户端请求无法覆盖 `TraceDatasourceTarget` 中的结果表。

## 0x05 实施进展

| 时间 | 结论性进展 |
| --- | --- |
| `2026-08-09 09:00` | 统一 Span 接口命名、里程碑和 `/rum/search/{API}/` 路由 |
| `2026-08-08 16:00` | 统一 Level 方法的参数、返回类型、命名和扩展边界 |
| `2026-08-07 19:00` | 完成分层设计：Level 以 `data_sources` 初始化，并可组合主查询与 Span 兜底查询 |

## 0x06 参考

- [<源码> bk-monitor/bkmonitor/data_source/utils/apm.py](https://github.com/TencentBlueKing/bk-monitor/blob/2067bb6ca8df7f7485c4583010919f21d80d29e8/bkmonitor/bkmonitor/data_source/utils/apm.py)
- [<源码> bk-monitor/bkmonitor/data_source/utils/query.py](https://github.com/TencentBlueKing/bk-monitor/blob/2067bb6ca8df7f7485c4583010919f21d80d29e8/bkmonitor/bkmonitor/data_source/utils/query.py)
- [<源码> bk-monitor/packages/rum_web/handlers/query/span.py](https://github.com/TencentBlueKing/bk-monitor/blob/2067bb6ca8df7f7485c4583010919f21d80d29e8/bkmonitor/packages/rum_web/handlers/query/span.py)
- [<源码> bk-monitor/packages/apm_web/trace/views.py](https://github.com/TencentBlueKing/bk-monitor/blob/2067bb6ca8df7f7485c4583010919f21d80d29e8/bkmonitor/packages/apm_web/trace/views.py)
- [RUM 数据协议](../../articles/2026-07-12-rum-span-data-protocol/README.md)

## 0x07 版本锚点

| 状态 | 分支 | 里程碑 | PR |
| --- | --- | --- | --- |
| 🔄 | `<branch_name>` | 里程碑 1：提供 RUM Span 列表类接口（`list_records`、`view_config`、`get_fields_option_values`、`generate_query_string`） | 待创建 |
| 🔄 | `<branch_name>` | 里程碑 2：提供 RUM Span 分析类接口（`field_topk`、`field_statistics_info`、`field_statistics_graph`、`download_topk`） | 待创建 |
| 🔄 | `<branch_name>` | 里程碑 3：提供 RUM Span 详情类接口（`record_detail`、`generate_query_string`） | 待创建 |
