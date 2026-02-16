# RPC 指标规范

## 1. 通用维度

| 维度                 | 维度名        | 示例                             | 备注                                                                                               |
|--------------------|------------|--------------------------------|--------------------------------------------------------------------------------------------------|
| **rpc_system**     | RPC 系统     | `trpc`                         | 支持传入自定义值，e.g. `trpc` / `tars`                                                                    |
| **scope_name**     | 指标分组名      | `server_metrics`               | 被调：`server_metrics`<br />主调：`client_metrics`                                                     |
| **service_name**   | 服务名        | ``example.greeter``            | --                                                                                               |
| **instance**       | 实例         | `127.0.0.1`                    | 取自 tRPC 配置（`global.local_ip`）。                                                                   |
| **container_name** | 容器名        | `gamesvr-01`                   | 取自 tRPC 配置（`global.container_name`）。                                                             |
| **namespace**      | 物理环境       | `Production`                   | 环境类型，取自 tRPC 配置（`global.namespace`）。一般取值：<br />- `Production` - 正式环境<br />- `Development` - 开发环境 |
| **env_name**       | 用户环境       | `dev`                          | 取自 tRPC 配置（`env_name`）。                                                                          |
| caller_server      | 主调服务       | `example.greeter`              | --                                                                                               |
| caller_service     | 主调 Service | `trpc.example.greeter.Greeter` | --                                                                                               |
| caller_con_setid   | 主调 SetID   | `set.sz.group1`                | --                                                                                               |
| caller_container   | 主调容器       | `gamesvr-01`                   | --                                                                                               |
| caller_ip          | 主调 IP      | `127.0.0.1`                    | --                                                                                               |
| caller_method      | 主调接口       | `SayHi`                        | --                                                                                               |
| callee_server      | 被调服务       | `example.greeter`              | --                                                                                               |
| callee_service     | 被调 Service | `trpc.http.server.service`     | --                                                                                               |
| callee_con_setid   | 被调 SetID   | `set.sz.group1`                | --                                                                                               |
| callee_container   | 被调容器       | `gamesvr-01`                   | --                                                                                               |
| callee_ip          | 被调 IP      | `127.0.0.1`                    | --                                                                                               |
| callee_method      | 被调接口       | `SayHello`                     | --                                                                                               |
| code               | 返回码        | `err_1`                        | 分为业务错误码和框架错误码。                                                                                   |
| code_type          | 返回码类型      | `success`                      | 页面的成功 / 超时 / 异常率通过该字段进行计算，取值：<br />- `success` - 成功<br />- `timeout` 超时<br />- `exception` 异常    |

* caller_xxx 维度表示主调服务的信息，callee_xxx 维度表示被调服务的信息。
* 主调：客户端视角，当前服务作为调用方，调用其他服务。
* 被调：服务端视角，当前服务作为被调用方，被其他服务调用。


## 2. 指标

### 2.1 主调指标

当服务作为客户端，调用其他服务的某个接口时，会通过主调指标记录打点。

| 指标                                | 描述      | 备注 |
|-----------------------------------|---------|----|
| rpc_client_handled_total          | 请求量     |    |
| rpc_client_handled_seconds_bucket | 耗时分桶    |    |
| rpc_client_handled_seconds_count  | 请求数（分桶） |    |
| rpc_client_handled_seconds_sum    | 请求耗时    |    |

### 2.2 被调指标

当服务作为服务端，被调用其他服务调用时，会通过被调指标记录打点。

| 指标                                | 描述      | 备注 |
|-----------------------------------|---------|----|
| rpc_server_handled_total          | 请求量     |    |
| rpc_server_handled_seconds_bucket | 耗时分桶    |    |
| rpc_server_handled_seconds_count  | 请求数（分桶） |    |
| rpc_server_handled_seconds_sum    | 请求耗时    |    |


### 2.3 RED 指标计算

#### 2.3.1 Galileo SDK

Galileo SDK 指标类型为 `Gauge`，需要使用 `sum_over_time` 计算，调用 `calculate_by_range` 时，`options.trpc.temporality` 需设置为 `delta`。

请求量：

```shell
sum(sum_over_time(rpc_client_handled_total{service_name="example.greeter"}[1m]))
```

request_total（成功率）：

````shell
sum(sum_over_time(rpc_client_handled_total{service_name="example.greeter", code_type="success"}[1m])) / sum(sum_over_time(rpc_client_handled_total{service_name="example.greeter"}[1m]))
````

平均耗时（success_rate）：

```shell
sum(sum_over_time(rpc_client_handled_seconds_sum{service_name="example.greeter", code_type="success"}[1m])) / sum(sum_over_time(rpc_client_handled_seconds_count{service_name="example.greeter"}[1m]))
```

耗时分布（P99）：

```shell
histogram_quantile(0.99, sum(sum_over_time(rpc_client_handled_seconds_bucket{service_name="example.greeter"}[1m])) by (le))
```



#### 2.3.2 Oteam SDK

OTeam SDK 指标类型为 `Counter`，需要使用 `increase` 计算，调用 `calculate_by_range` 时，`options.trpc.temporality` 需设置为 `cumulative`。

请求量：

```shell
sum(increase(rpc_client_handled_total{service_name="example.greeter"}[1m]))
```

成功率：

````shell
sum(increase(rpc_client_handled_total{service_name="example.greeter", code_type="success"}[1m])) / sum(increase(rpc_client_handled_total{service_name="example.greeter"}[1m]))
````

平均耗时

```shell
sum(increase(rpc_client_handled_seconds_sum{service_name="example.greeter", code_type="success"}[1m])) / sum(increase(rpc_client_handled_seconds_count{service_name="example.greeter"}[1m]))
```

耗时分布（P99）：

```shell
histogram_quantile(0.99, sum(increase(rpc_client_handled_seconds_bucket{service_name="example.greeter"}[1m])) by (le))
```
