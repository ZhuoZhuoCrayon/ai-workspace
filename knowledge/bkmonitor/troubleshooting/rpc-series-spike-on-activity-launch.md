---
title: 0 点活动上线导致 RPC 指标 series 暴涨
tags: [apm, rpc, cardinality, series-spike, callee-container, sum-without-ip, fan-out, dormant-series]
description: 通过 ΔC 边对比、维度拆解与 VM 新增 series 验证，定位活动上线引发的 RPC 指标 series 暴涨；区分业务新值、潜伏 series 与高基数扇出乘子。
created: 2026-04-25
updated: 2026-08-08
---

# 0 点活动上线导致 RPC 指标 series 暴涨

## 0x01 排查方法

### a. 适用场景

- APM 应用 RPC 指标在某个时间点（如活动上线、版本发布）出现 series 数突增。
- 原始 `rpc_*_handled_total` 自身基数已过高，无法直接用于分析。
- 业务侧通常已沉淀一份去 IP 的业务自定义指标（如 `sum_without_ip_rpc_client_handled_total`），分析以业务自定义指标为入口。
- 对端 trace 已过期，只能基于指标做归因。

### b. 名词约定

- **边**：`(service_name, callee_service)` 取值的一对组合
  - 本文最小的分析单元，一条边对应主调端发出 / 被调端接收的一组 series
- **驱动维度（driver）**：该边上 0 点后真正出现新值的维度，是业务诱因。
- **扇出乘子（multiplier，fan-out）**：该边上值集合不变、但提供倍数放大的高基数维度（如 `callee_container`）。
- **R**：上报该指标的服务副本数
  - 本文计算「ΔC × R = 新增 series」

### c. 排查步骤

#### 步骤 1：用 `count by (service_name, callee_service)` 在两个相邻窗口对比 ΔC

定位所有「边」上的新增/放大。

窗口选 0 点前后各 30 min，range vector 取 `[30m]` 与窗口对齐。

```promql
# 窗口 A: 突增前
count by (service_name, callee_service) (
  sum_over_time( <metric>{ ... }[30m] )
)
```

`ΔC = C[突增后] − C[突增前]`：

- `C_before = 0, C_after > 0` → 全新边。
- `C_before > 0, C_after >> C_before` → 已有边被放大。

#### 步骤 2：倒查每条新边的上游

对每个新增 `callee_service`，去掉 `service_name` 过滤，找出真正的主调，确定调用入口：

```promql
count by (service_name, callee_service) (
  sum_over_time( <metric>{ callee_service="<新边的 callee>" }[30m] )
)
```

新边可能挂在已有的入口服务下，识别清楚才能正确解读「为什么这些活动同时开始上报」。

#### 步骤 3：先把每条新增/放大的边分类

| 类型        | 判定                                  | 含义                                                            |
|-----------|-------------------------------------|---------------------------------------------------------------|
| **全新边**   | `C_before = 0, C_after > 0`         | 前 30 min 完全未上报，0 点出现的 series 全是「新值」，直接看哪个维度的扇出（fan-out）倍数最大 |
| **已有边放大** | `C_before > 0, C_after >> C_before` | 前 30 min 已稳态运行，0 点 ΔC 突变，需要分辨「新值驱动」与「扇出乘子」                    |

两类边的归因路径完全不同，混在一起讲会得出错误结论。

#### 步骤 4：识别隐藏维度

业务自定义指标通常只去掉 IP 相关 label，但其他高基数 label（如被调 pod 名）可能被遗漏。用 `topk` 拉若干条业务自定义指标 series，对比它们的全部维度键值：

```promql
topk(5, sum_over_time( <metric>{ <边> }[1h] ))
```

观察 5 条 series 中「其他维度全相同、仅某一维度在变」的那一列即为隐藏维度，它通常就是后续步骤里的扇出乘子候选。

#### 步骤 5：分辨「新值驱动」与「扇出乘子」

仅对「已有边放大」做。对每个候选维度独立跑 `count by`，跨 0 点：

```promql
count by (<dim>) (sum_over_time( <metric>{ <边> }[1m] ))
```

| 现象                        | 维度角色                | 处理                                 |
|---------------------------|---------------------|------------------------------------|
| 维度值集合**扩大**（0 点后出现新值）     | **新值驱动**——真正诱因      | 重点关注是哪个新值（如新 `code`、新 `user_ext1`） |
| 维度值集合**不变**，但每个值的覆盖率/频次提升 | **扇出乘子**——基数放大器     | 关注去除它能消减多少 series                  |
| 维度只有少数固定值且不变              | 无关                  | 忽略                                 |

确认新值之间的乘法关系：

```promql
count by (<新值维度 1>, <新值维度 2>) (
  sum_over_time( <metric>{ <边> }[1m] )
)
```

> **常见误区**：高基数维度（如 ≈ 800 个 pod 名）很容易被误标为「真正诱因」，但若窗口内值集合不变它只是乘子——去掉收益巨大却无法解释 0 点为何突变，真正诱因永远在新值驱动里

#### 步骤 6：把 ΔC 换算成上报 series 上限

`新增 series 上限 ≈ ΔC × R`，R 取上报该指标的服务副本数：

- 主调端（发出 `rpc_client_handled_total`）：`R = 主调副本数`。
- 被调端（发出 `rpc_server_handled_total`）：`R = 被调副本数`，仅当被调在本 APM 内上报 `rpc_server_handled_total` 时才计入，外部被调不入账。

获取某个服务在目标窗口内的上报副本：

```promql
sum by (instance) (
  sum_over_time( <metric>{ service_name="xxx" }[1m] )
)
```

返回结果的 `instance` 行数即 `R`。

如果需要直接返回副本数，可外层再套一层 `count(...)`：

```promql
count(
  sum by (instance) (
    sum_over_time( <metric>{ service_name="xxx" }[1m] )
  )
)
```

约束：

- 原始 `rpc_*_handled_*` 只允许用于查询 `R`。
- 禁止用原始指标的 `count(...)`、差值或分组结果计算基数增量。
- `ΔC`、维度基数和边贡献一律来自业务自定义指标。

#### 步骤 7：跨 metric 家族放大

每条 `(edge × label combo)` 在 4 类 RPC metric 上同时上报，实际 series 数 = 单 metric × 乘子：

```text
乘子 = 1 × _total + 1 × _seconds_count + 1 × _seconds_sum + N × _seconds_bucket
N = 直方图 le 标签的取值数（含 +Inf）
```

N 由指标 schema 或 callee 应用的 histogram 配置确认。

本案例 N=10，乘子 = 13。

#### 步骤 8：用 series 新增数量指标做回归验证

目的：用监控系统侧（VictoriaMetrics，下文简称 VM）记录的「每分钟新增 series 数」对齐分析结论，并在缓解动作落地后做回归。

```promql
sum(increase(bkmonitor:vm_new_timeseries_created_total{bk_monitor_name="monitor-hpjyapm-servicemonitor"}[1m]))
```

- 观察新增 series 数的时间分布，验证增量是否与分析结论吻合（0 点前后突增、持续时间与分析窗口对齐）。
- 使用 bkop MCP，查询业务 ID 填 `10`。
- MCP 环境约束：
  - 只有 VM 新增 series 这一条 PromQL 使用 bkop MCP。
- 其他边级、维度级和副本数查询统一使用 bkte MCP。
- 缓解动作发布后，再次拉这条曲线，下次活动 0 点应回到非活动日水位即视为生效。

### d. 结果输出建议

- 用一棵以入口服务为顶点的拓扑树展示所有受影响边，按类型标注：
  - `[NEW SERVICE]` / `[NEW EDGE]`：边在 0 点前完全未上报。
  - `driver: <维度>`：该边上 0 点后出现新值的维度（业务诱因）。
  - `multiplier: <维度>`：该边上值集合不变、但提供倍数放大的高基数维度。
- 总账分主调端 / 被调端 / 单 metric / 跨 4 类 metric 四列。
- 优化建议按 `service_name + 去除维度` 描述，按节省量降序，给出单次 PR 可砍多少。

## 0x02 结论（本案）

> - 业务：APM 应用 `hpjy-microservices-activities-production`（biz_id `-4228598`）
> - 时间：`2026-02-16 00:00 +0800`
> - 分析指标：`sum_without_ip_rpc_client_handled_total`
> - 副本数：
>   - `msgcenter`=480，`msgcenter-camp`=40
>   - `activities-{10139,10206,10212,10221}`=240
>   - `activities-60017`=120，其他 `activities-*`=120
> - histogram bucket：`le` 标签 10 个值（含 `+Inf`），跨 4 类 RPC metric 乘子 = 13

### a. TL;DR

- **现象**：0 点单 metric 新增 ≈ 616 K series，跨 4 类 RPC metric ≈ 8.0 M。
- **真正诱因**：`activities-60017` / `activities-10221` 调向 AMS 域被调的 3 条边
  - `amspkg` / `campamspkg` / `amshostpkg`，合计 ≈ 467 K（76 %）
  - AMS 域被调指标里带 `callee_container`（被调 pod 名，≈ 800 个值），构成 800 倍扇出乘子
- **缓解动作**：给这两个服务的业务自定义指标追加去除 `callee_container`
  - 单次 PR 即可消减 ≈ 467 K / 6.08 M
- **用户原始线索**：`activities-10139` / `activities-10206` 链路只占 ≈ 60 K（10 %）
  - 引入的下游边都是低基数（`redis-data` / `msgcenter` / `msgcenter.forward`），不是大头

### b. 调用拓扑

0 点 16 个 activities 子服务经统一入口 `msgcenter` / `msgcenter-camp` 同时开始上报，自身边的 ΔC 上升，并连带下游被调的 ΔC 一起上升。

`ΔC = C[00:00, 00:30] − C[23:30, 00:00]`。

格式：

- `[service_name=…]` 是主调（上报指标的服务 + 副本数）。
- `--> callee_service=…` 是它的一条出边。

```text
[service_name=activity-microservices.msgcenter]   (R=480)
├── --> callee_service=trpc.hpjy.activity-microservices.activities.10139         ΔC=25  [NEW SERVICE]
│
│   [service_name=activity-microservices.activities-10139]   (R=240)
│   ├── --> callee_service=trpc.hpjy.activity-microservices.redis-data           ΔC=56   driver: user_ext1=act_10139_{assist|roll|send}_req
│   ├── --> callee_service=trpc.hpjy.activity-microservices.msgcenter            ΔC=8
│   └── --> callee_service=trpc.hpjy.activitymicroservices.msgcenter.forward     ΔC=7
│
├── --> callee_service=trpc.hpjy.activity-microservices.activities.10206         ΔC=16  [NEW SERVICE]
│
│   [service_name=activity-microservices.activities-10206]   (R=240)
│   ├── --> callee_service=trpc.hpjy.activity-microservices.redis-data           ΔC=54   driver: user_ext1=act_10206_{click|feed}_req
│   ├── --> callee_service=trpc.hpjy.activity-microservices.msgcenter            ΔC=9
│   └── --> callee_service=trpc.hpjy.activitymicroservices.msgcenter.forward     ΔC=1
│
├── --> callee_service=trpc.hpjy.activity-microservices.activities.10212         ΔC=4
│   [service_name=activity-microservices.activities-10212]   (R=240)
│   └── --> callee_service=trpc.hpjy.activity-microservices.redis-data           ΔC=38   driver: user_ext1=act_10212_*_req
│
├── --> callee_service=trpc.hpjy.activity-microservices.activities.10221         ΔC=5
│   [service_name=activity-microservices.activities-10221]   (R=240)
│   ├── --> callee_service=trpc.hpjy.activity-microservices.amshostpkg           ΔC=899  [NEW EDGE] driver: callee_container ≈800 pods
│   ├── --> callee_service=trpc.hpjy.activity-microservices.redis-data           ΔC=40   driver: user_ext1=act_10221_*_req
│   ├── --> callee_service=trpc.hpjy.activitymicroservices.msgcenter.forward     ΔC=7
│   └── --> callee_service=trpc.hpjy.activity-microservices.msgcenter            ΔC=1
│
├── --> callee_service=trpc.hpjy.activity-microservices.activities.{10078,10101,10119,10129,10143,
│                                                                    10144,10158,10177,10209,10211,
│                                                                    10222,80007}                    ΔC合计=49
├── --> callee_service=trpc.hpjy.activity-microservices.producer_sq              ΔC=8
├── --> callee_service=trpc.hpjy.activity-microservices.producer_wx              ΔC=8
└── --> callee_service=trpc.cj.trpc2s.activitysvr                                ΔC=4

[service_name=activity-microservices.msgcenter-camp]   (R=40)
├── --> callee_service=trpc.hpjy.activity-microservices.activities.60009         ΔC=1
├── --> callee_service=trpc.hpjy.activity-microservices.activities.60014         ΔC=1
└── --> callee_service=trpc.hpjy.activity-microservices.activities.60017         ΔC=4
    [service_name=activity-microservices.activities-60017]   (R=120)
    ├── --> callee_service=trpc.hpjy.activity-microservices.amspkg               ΔC=1293 已有边放大 540→2601；driver: code=err_101 + user_ext1=check_in_req；multiplier: callee_container ≈800 pods
    ├── --> callee_service=trpc.hpjy.activity-microservices.campamspkg           ΔC=800  [NEW EDGE] driver: callee_container ≈800 pods
    ├── --> callee_service=hpyd.php.inner.formal                                 ΔC=233  [NEW EDGE] driver: callee_method × user_ext1=act_60017_*
    ├── --> callee_service=trpc.hpjy.activity-microservices.redis-data           ΔC=16
    └── --> callee_service=trpc.hpjy.activitymicroservices.msgcenter.forward     ΔC=1
```

图例：

- `[NEW SERVICE]` / `[NEW EDGE]`：当晚首次上线的服务或当晚首次出现的调用边，所有 series 都是新值。
- `driver`：该边上真正出现新值的维度，是业务诱因。
- `multiplier`：该边上值集合不变、但提供倍数放大的高基数维度（去除后 ΔC 大幅消减）。

未跟进项（占比小且与活动 0 点共振，本期未深入）：

- `60017` → `hpyd.php.inner.formal` ΔC=233 [NEW EDGE]：≈ 28 K series，驱动维度初判为 `callee_method × user_ext1`，未单独验证。
- `msgcenter` → 12 个其他活动子服务 ΔC 合计 49：≈ 23.5 K series，都是常规活动入口流量。
- 这两项 0 点新增合计约 51 K（< 9 %），已纳入「其他放量」总账，不单独跑 PromQL 拆解。

### c. 关键边 series 跳变佐证

`step=1m`，窗口 `2026-02-15 23:50 → 2026-02-16 00:09 +0800`，单位 = 该 1 min 内边上的独立 series 数。

#### c.1 入口边：`msgcenter` → `activities.{10139, 10206, 10221}`

```promql
count by (callee_service) (
  sum_over_time(sum_without_ip_rpc_client_handled_total{
    service_name="activity-microservices.msgcenter",
    callee_service=~"trpc.hpjy.activity-microservices.activities.10139|trpc.hpjy.activity-microservices.activities.10206|trpc.hpjy.activity-microservices.activities.10221"
  }[1m])
)
```

| `callee_service` | 23:50 ~ 23:59 | 00:00 | 00:01 峰值 | 00:02 ~ 00:09 稳态 | 类型 |
| --- | ---: | ---: | ---: | ---: | --- |
| `activities.10139` | null | 2 | 22 | 18 ~ 24 | 全新边 |
| `activities.10206` | null | 2 | 12 | 10 ~ 15 | 全新边 |
| `activities.10221` | 17 ~ 19 | 18 | 19 | 19 ~ 23 | 已有边轻微放大 |

#### c.2 多活动放大边：`activities-*` → `redis-data`

```promql
count by (service_name, callee_service) (
  sum_over_time(sum_without_ip_rpc_client_handled_total{
    service_name=~"activity-microservices.activities-10139|activity-microservices.activities-10206|activity-microservices.activities-10212|activity-microservices.activities-10221",
    callee_service="trpc.hpjy.activity-microservices.redis-data"
  }[1m])
)
```

| `service_name`     | 23:50 ~ 23:59 | 00:00 | 00:01 峰值 | 00:04 峰值 | 00:02 ~ 00:09 稳态 |
|--------------------|--------------:|------:|---------:|---------:|-----------------:|
| `activities-10139` |             7 |    11 |       44 |       63 |               44 |
| `activities-10206` |             9 |     9 |       40 |       64 |               40 |
| `activities-10212` |            60 |    60 |       60 |       87 |          59 ~ 60 |
| `activities-10221` |           108 |   111 |      124 |      135 |        108 ~ 117 |

驱动维度是 `user_ext1=act_<id>_<action>_req`，每个活动开放后会出现一组新的 `<action>`，叠加在原有 redis 调用上。

#### c.3 全新边：`callee_container` 直接展开为 800 倍

`10221 → amshostpkg` 与 `60017 → campamspkg` 是当晚首次出现的边，0 点前 series 数为 0，0 点后一次性出现 ≈ 800 个 `callee_container` 值，构成新值本身。

```promql
count by (service_name, callee_service, callee_container) (
  sum_over_time(sum_without_ip_rpc_client_handled_total{
    service_name=~"activity-microservices.activities-10221|activity-microservices.activities-60017",
    callee_service=~"trpc.hpjy.activity-microservices.amshostpkg|trpc.hpjy.activity-microservices.campamspkg"
  }[1m])
)
```

| `service_name` → `callee_service` | 23:59 distinct container | 00:01 distinct container | 类型 |
| --- | ---: | ---: | --- |
| `10221` → `amshostpkg` | 0 | ≈ 800 | [NEW EDGE]，container 即驱动 |
| `60017` → `campamspkg` | 0 | ≈ 600 | [NEW EDGE]，container 即驱动 |

这两条边里 `callee_container` 既是新值也是扇出来源，去除它能消减全部增量。

#### c.4 已有边放大：辨析驱动维度 vs 扇出乘子（`60017 → amspkg`）

这条边 23:50 已有 ≈ 440 series 稳态，0:01 跳到 2601，乍看像 `callee_container` ≈ 800 pod 主导，但拉开看 container 值集合在 0 点前后基本不变——它是乘子，不是驱动。

##### 步骤 1：先看 `callee_container` 值集合是否扩大

```promql
count by (service_name, callee_service, callee_container) (
  sum_over_time(sum_without_ip_rpc_client_handled_total{
    service_name="activity-microservices.activities-60017",
    callee_service="trpc.hpjy.activity-microservices.amspkg"
  }[1m])
)
```

| 指标               | 23:50 ~ 23:59 | 00:00 ~ 00:09 |
|------------------|--------------:|--------------:|
| 累积去重 container 数 |           799 |           800 |
| 两窗口交集            |             — |           799 |

> 30 min 窗口内 container 集合几乎不变（只多 1 个）——**容器不是新值，是乘子**

##### 步骤 2：找真正出现新值的维度

依次跑 `count by (<dim>)` 跨 0 点，对比每个候选维度的值集合：

| 维度                        | 23:59 已有值               | 00:01 新增值                        | 角色       |
|---------------------------|-------------------------|----------------------------------|----------|
| `code`                    | `0`                     | `err_101`（活动期错误码）                | **新值驱动** |
| `user_ext1`               | `act_60017_lottery_req` | `act_60017_check_in_req`（新增业务动作） | **新值驱动** |
| `callee_method`           | 12 个固定方法                | 0                                | 无关       |
| `caller_method`           | 4 个固定方法                 | 0                                | 无关       |
| `user_ext2` / `user_ext3` | 单值                      | 0                                | 无关       |

##### 步骤 3：按 `code` × `user_ext1` 分组拆解每个新值的贡献

```promql
count by (code, user_ext1) (
  sum_over_time(sum_without_ip_rpc_client_handled_total{
    service_name="activity-microservices.activities-60017",
    callee_service="trpc.hpjy.activity-microservices.amspkg"
  }[1m])
)
```

| (`code`, `user_ext1`) 组合 | 23:50 ~ 23:59 series | 00:01 series | Δseries | 占增量比 | 类型 |
| --- | ---: | ---: | ---: | ---: | --- |
| `0` × `lottery_req` | 410 | 799 | +389 | 19 % | 已有组合，container 覆盖率扩大 |
| `0` × `check_in_req` | 30 | 757 | +727 | 35 % | **新值驱动**：`check_in_req` 业务上线 |
| `err_101` × `lottery_req` | 0 | 719 | +719 | 35 % | **新值驱动**：`err_101` 错误码出现 |
| `err_101` × `check_in_req` | 0 | 326 | +326 | 16 % | 两个新值叠加 |
| **合计** | **440** | **2601** | **+2161** | 100 % | — |

- 两个新值（`code=err_101` 与 `user_ext1=check_in_req`）合计贡献 86 % 的增量
- 剩余 19 % 是已有组合 `(0, lottery_req)` 的 container 覆盖率从 410 涨到 799
  - 0 点活动量起来后，原本只有部分 pod 命中的 `lottery_req` 被打到几乎全部 ≈ 800 个 pod
  - 扇出乘子在更多 container 上同时上报，与新值无关

##### 结论

- 真正诱因：活动期上线 `check_in_req` 业务动作 + 引入 `err_101` 错误码
- 真正放大器：800 个 `callee_container` 把每个新值放大 800 倍
- 缓解动作：
  - 去除 `callee_container`，直接砍掉 800 倍扇出，无论上层维度新增什么都展开不出来
  - 再追加「`code != 0` 时才上报 `user_ext1`」的业务方上报规则，可压缩残余增量

### d. 总账

`新增 series ≈ ΔC × R`，R 取上报该指标的服务副本数：

- 主调端（发出 `rpc_client_handled_total`）：R = 主调服务副本
- 被调端（发出 `rpc_server_handled_total`）：R = 被调服务副本
  - 本 APM 仅 `msgcenter` / `msgcenter-camp` 上报 `rpc_server_handled_total`，其他被调不计入

#### d.1 单 metric 与跨 4 类总账

| 范围                                                                          |         主调端 |         被调端 | 单 metric 合计 | 跨 4 类 RPC metric 合计 |
|-----------------------------------------------------------------------------|------------:|------------:|------------:|--------------------:|
| `10139` / `10206` 链路                                                        |      52.1 K |       8.1 K |      ≈ 60 K |            ≈ 0.78 M |
| 其他放量（`10212` / `10221` / `60017` / `msgcenter` / `msgcenter-camp`）            |     555.3 K |       0.5 K |     ≈ 556 K |            ≈ 7.23 M |
| **合计**                                                                      | **≈ 607 K** | **≈ 8.6 K** | **≈ 616 K** |         **≈ 8.0 M** |

跨 4 类乘子的来源：

- 计数类：`client._total` / `client._seconds_count` / `client._seconds_sum`，各贡献 1 倍
- 直方图：`client._seconds_bucket`，每个 `le` 值一条 series，本案 `le` 共 10 个值（含 `+Inf`）
- 合计乘子 = 1 + 1 + 1 + 10 = **13**
- 被调端 8.6 K 同样按该乘子展开（≈ 0.11 M），已合并到上表「跨 4 类 RPC metric 合计」列

#### d.2 按主调服务逐项

出边明细见 `b. 调用拓扑` 中各主调子树的 `--> callee_service=…  ΔC=…` 行。

| 主调 `service_name`       |   R |    ΔC 合计 |  主调端 series |
|-------------------------|----:|---------:|------------:|
| `msgcenter`             | 480 |      119 |      57.1 K |
| `msgcenter-camp`        |  40 |        6 |      0.24 K |
| `activities-10139`      | 240 |       71 |      17.0 K |
| `activities-10206`      | 240 |       64 |      15.4 K |
| `activities-10212`      | 240 |       38 |       9.1 K |
| `activities-10221`      | 240 |      947 |     227.3 K |
| `activities-60017`      | 120 |     2343 |     281.2 K |
| **主调端合计**               |   — | **3588** | **≈ 607 K** |

### e. 缓解动作

#### e.1 动作清单

按节省量降序，所有动作落点都在业务自定义 `sum_without_ip_*` 的去除规则中追加新维度：

| 主调 `service_name` | 去除维度 | 单 metric 节省 | 跨 4 类 metric 节省（×13） | 期次 |
| --- | --- | ---: | ---: | --- |
| `activity-microservices.activities-60017` | `callee_container` | ≈ 251 K | ≈ 3.27 M | 一期 |
| `activity-microservices.activities-10221` | `callee_container` | ≈ 216 K | ≈ 2.81 M | 一期 |
| `activity-microservices.activities-*`（全部活动服务） | `user_ext1` | ≈ 17 K | ≈ 0.22 M | 二期 |

一期合计：**≈ 467 K（占 0 点单 metric 新增量 76 %）/ ≈ 6.08 M 跨 4 类**。

- 单次 PR 即可发起
- 落地后预计 VM 入库延迟回到非活动日水位
- 用 `0x01 c. 步骤 8` 的 PromQL 做回归

二期 `user_ext1`（≈ 17 K / ≈ 0.22 M，< 3 %）留作业务监控诉求一并评估，单独发起意义不大。

#### e.2 一期收益拆解

- **`activities-60017` 去除 `callee_container`**（R=120，合计 ≈ 251 K）：
  - `60017` → `campamspkg`（800 ΔC × 120 = 96 K，[NEW EDGE]）：800 个 container 是真新值，去除后整条边收敛
  - `60017` → `amspkg`（1293 ΔC × 120 = 155 K，已有边放大）：
    - container 是 800 倍扇出乘子
    - 去除后即使 `code=err_101` 与 `user_ext1=check_in_req` 等新值继续出现，也只能各产生一条 series，整条边压回个位数
- **`activities-10221` 去除 `callee_container`**（R=240，合计 ≈ 216 K）：
  - `10221` → `amshostpkg`（899 ΔC × 240 = 216 K，[NEW EDGE]）：消减 ≈ 800 个被调 pod 名展开

> 去除 `callee_container` 这一动作对「已有边放大」场景的价值远高于直觉——它不依赖预测业务会上什么新动作或新错误码，而是直接砍掉乘子，对未来类似活动也免疫

## 0x03 结论（元旦本案）

> - 业务：APM 应用 `hpjy-microservices-activities-production`（biz_id `-4228598`）
> - 时间：`2026-01-01 00:00 +0800`
> - 对比窗口：`2025-12-31 23:30 ~ 2026-01-01 00:00` vs `2026-01-01 00:00 ~ 00:30`
> - 分析指标：`sum_without_ip_rpc_client_handled_total`
> - 验证指标：`bkmonitor:vm_new_timeseries_created_total`
> - 指标 RT：
>
> ```text
> custom:space_4228598_bkapm_metric_hpjy__bk_45__microservices__bk_45__activities__bk_45__production:__default__
> ```
>
> - 说明：`ΔC` 表示业务自定义指标组合数增量，`R` 表示 0 点窗口内上报实例数

### a. TL;DR

- **实际现象**：VM 侧 `00:00 ~ 00:30` 新增 `3.68 M` series，较前 30 min 基线额外增加 `≈ 2.39 M`。
- **峰值时刻**：`00:00` 单分钟新增 `724.5 K`，与元旦活动上线时间对齐。
- **主因**：`activities-60013` 红包链路新增 `60013 -> campamspkg` 调用边。
- **放大器**：`callee_container` 从 `0` 展开到 `400`，是本次最大高基数维度。
- **次级来源**：`60013` / `60009` 调向 `hpyd.php.inner.formal` 扩量，以及多活动服务调向 `redis-data` 时出现 `err_101`。

### b. 调用拓扑

```text
[service_name=activity-microservices.activities-60013] (R=240)
├── --> callee_service=trpc.hpjy.activity-microservices.campamspkg
│   ├── ΔC=400  [NEW EDGE]
│   ├── driver: user_ext1=act_60013_redpacket_req, code=0, callee_method=/main
│   └── multiplier: callee_container 0 -> 400
│
├── --> callee_service=hpyd.php.inner.formal
│   ├── ΔC=247
│   ├── driver: act_60013_redpacket_req / act_60013_roll_dice_req / ret_0 扩量
│   └── multiplier: callee_container 50 -> 63，非主因
│
└── --> callee_service=trpc.hpjy.activity-microservices.redis-data
    ├── ΔC=38
    └── driver: code=err_101

[service_name=activity-microservices.activities-60009] (R=240)
├── --> callee_service=hpyd.php.inner.formal
│   ├── ΔC=174
│   ├── driver: ret_0 扩量 + err_102 / err_161 新增
│   └── multiplier: callee_container 50 -> 63，非主因
│
└── --> callee_service=trpc.hpjy.activity-microservices.redis-data
    └── ΔC=18

[多活动服务]
└── --> callee_service=trpc.hpjy.activity-microservices.redis-data
    └── driver: code=err_101
```

图例：

- `[NEW EDGE]`：0 点前完全未上报，0 点后出现的新调用边。
- `driver`：该边上 0 点后出现或明显放大的业务维度。
- `multiplier`：把业务维度继续展开的高基数维度。

### c. 关键边 series 跳变佐证

| 边 | ΔC | R | `ΔC × R` 上限 | 角色 |
| --- | ---: | ---: | ---: | --- |
| `60013 -> campamspkg` | `400` | `240` | `96.0 K` | 主贡献边 |
| `60013 -> hpyd.php.inner.formal` | `247` | `240` | `59.3 K` | 主贡献边 |
| `60009 -> hpyd.php.inner.formal` | `174` | `240` | `41.8 K` | 二期治理边 |
| `10119 -> redis-data` | `59` | `480` | `28.3 K` | 业务错误码新值 |

`ΔC × R` 只表示风险上限。

实际入库量以 VM 曲线为准，因为同一组合不会在每个实例上完整展开。

### d. 总账

这部分只回答一个问题：监控系统实际多收了多少 series。

前面的边级拆解用于解释来源。

最终对外量级以 VM 实测为准。

| 窗口 | VM 新增 series | 分钟均值 | 峰值 |
| --- | ---: | ---: | ---: |
| `23:30 ~ 00:00` | `1.29 M` | `43.0 K/min` | `52.8 K` |
| `00:00 ~ 00:30` | `3.68 M` | `122.7 K/min` | `724.5 K` |
| `00:30 ~ 01:00` | `1.57 M` | `52.4 K/min` | `68.8 K` |

最终对外口径使用 VM 实测值：

```text
额外新增 series ≈ 3.68 M - 1.29 M = 2.39 M
```

### e. 缓解动作

按 `0x02 e. 缓解动作` 的模板计算：单 metric 节省 = `ΔC × R`，跨 4 类 RPC metric 节省 = 单 metric 节省 × `13`。

#### e.1 动作清单

| 主调 `service_name` | 去除维度 | 单 metric 节省 | 跨 4 类 metric 节省（×13） | 期次 |
| --- | --- | ---: | ---: | --- |
| `activity-microservices.activities-60013` | `callee_container` | ≈ 155 K | ≈ 2.02 M | 一期 |
| `activity-microservices.activities-60009` | `callee_container` | ≈ 42 K | ≈ 0.54 M | 二期 |

一期 `activities-60013` 合计：**≈ 155 K / ≈ 2.02 M，占 VM 额外新增 ≈ 84%**。

如果 `activities-60009` 同步处理，合计：**≈ 197 K / ≈ 2.56 M，理论上可覆盖本次 VM 额外新增**。

#### e.2 收益拆解

- **`activities-60013` 去除 `callee_container`**：
  - `60013 -> campamspkg`：`400 × 240 = 96.0 K`，跨 4 类约 `1.25 M`。
  - `60013 -> hpyd.php.inner.formal`：`247 × 240 = 59.3 K`，跨 4 类约 `0.77 M`。
- **`activities-60009` 去除 `callee_container`**：
  - `60009 -> hpyd.php.inner.formal`：`174 × 240 = 41.8 K`，跨 4 类约 `0.54 M`。

说明：

- 上述收益是与 `0x02` 保持一致的上限口径。
- `2.56 M` 高于 VM 实测额外新增 `2.39 M` 时，不写成超过 `100%`。
- 这只表示理论上覆盖本次全部增量，最终压缩效果以 `bkmonitor:vm_new_timeseries_created_total` 回归为准。

## 0x04 结论（10234 活动 10:24 本案）

> - 业务：APM 应用 `hpjy-microservices-activities-production`（biz_id `-4228598`）
> - 时间：`2026-04-29 10:24 +0800`
> - 分析窗口：`2026-04-29 10:10 ~ 10:40 +0800`
> - VM 新增 series 查询：使用 bkop MCP，业务 ID `10`
> - 其他 RPC 指标查询：使用 bkte MCP，业务 ID `-4228598`
> - 基数证据指标：`sum_without_ip_rpc_client_handled_total`
> - 原始 `rpc_client_handled_total` 只用于查询副本数 `R`

### a. TL;DR

- **实际现象**：VM 侧 `10:24` 单分钟新增 `181.2 K` series，`10:25` 仍有 `99.4 K`。
- **主因**：`activity-microservices.activities-10234` 活动拉起后，新增出边和 Redis 业务维度组合同时出现。
- **最大贡献边**：`10234 -> redis-data` 从 `20` 增至 `88`，`ΔC=68`。
- **放大链路**：`ΔC × R × RPC metric 家族乘子`，其中 `R=120`，乘子按 `0x02` 口径取 `13`。
- **总账结果**：按 `ΔC × R × 13` 得到约 `179.4 K`，贴近 bkop 侧 `181.2 K/min` 峰值。
- **差异点**：本案不是 `callee_container` 的 400/800 级高基数扇出，而是中等基数新值被实例数和 RPC metric 家族同步放大。

### b. 调用拓扑

```text
[service_name=activity-microservices.msgcenter] (R=240)
└── --> callee_service=trpc.hpjy.activity-microservices.activities.10234
    ├── ΔC=14  [NEW EDGE]
    └── driver: 10234 活动入口调用新增

[service_name=activity-microservices.activities-10234] (R=120)
├── --> callee_service=trpc.hpjy.activity-microservices.redis-data
│   ├── ΔC=68
│   ├── driver: user_ext1=act_10234_*_req 新增
│   ├── driver: caller_method 新增/扩量
│   └── driver: callee_method=SETEX 新增
│
├── --> callee_service=trpc.hpjy.activity-microservices.msgcenter
│   ├── ΔC=12  [NEW EDGE]
│   └── driver: 活动内部消息调用新增
│
├── --> callee_service=trpc.hpjy.activitymicroservices.msgcenter.forward
│   ├── ΔC=3  [NEW EDGE]
│   └── driver: 活动内部消息转发新增
│
├── --> callee_service=trpc.hpjy.10234.{getrecommfriend,getrndrecommfriend,sevenyear}
│   ├── ΔC=3  [NEW EDGE]
│   └── driver: 10234 活动内部服务调用新增
│
└── --> callee_service=trpc.hpjy.activity-microservices.activities.10234
    ├── ΔC=1  [NEW EDGE]
    └── driver: 10234 自调用新增
```

图例：

- `[NEW EDGE]`：`10:23` 未上报，`10:24 ~ 10:26` 出现的新调用边。
- `ΔC`：业务自定义指标在边上的组合数增量，禁止用原始 RPC 指标计算。
- `driver`：该边上新增或明显放大的业务维度。
- `R`：上报该指标的服务副本数。

### c. 维度拆解

最大边 `10234 -> redis-data` 按 `callee_method` 拆解如下：

| `callee_method` | 10:23 | 10:25 | 新增 |
| --- | ---: | ---: | ---: |
| `DEL` | `8` | `22` | `14` |
| `EVAL` | `8` | `22` | `14` |
| `GET` | `4` | `22` | `18` |
| `SETEX` | `0` | `22` | `22` |
| 合计 | `20` | `88` | `68` |

业务驱动来自 `user_ext1=act_10234_*_req` 和 `caller_method` 扩展。

它们是同一批 `68` 个增量的不同切片，不能相加。

`code` 全部是 `0`，不是错误码放大。

### d. 总账

按 `0x02` 口径计算：单 metric 上限 = `ΔC × R`，跨 RPC metric 家族新增 = 单 metric 上限 × `13`。

| 来源 | ΔC | R | 单 metric 上限 | 跨 RPC metric 家族（×13） |
| --- | ---: | ---: | ---: | ---: |
| `10234 -> redis-data` | `68` | `120` | `≈ 8.2 K` | `≈ 106 K` |
| `10234 -> msgcenter` | `12` | `120` | `≈ 1.4 K` | `≈ 18.7 K` |
| `10234 -> msgcenter.forward` | `3` | `120` | `≈ 0.36 K` | `≈ 4.7 K` |
| `10234 -> 内部 10234 服务` | `4` | `120` | `≈ 0.48 K` | `≈ 6.2 K` |
| `msgcenter -> 10234` | `14` | `240` | `≈ 3.4 K` | `≈ 43.7 K` |
| 合计 | — | — | `≈ 13.8 K` | `≈ 179.4 K` |

与 bkop 侧 `10:24` 的 `181.2 K/min` 差异来自分钟对齐、采集落点和不同 RPC metric 的实际展开。

### e. 缓解动作

- 短期仅看降 series：优先评估 `activities-10234 -> redis-data` 是否需要保留 `user_ext1`。
- 去除 `user_ext1` 可消减约 `32 × 120 ≈ 3.8 K` 单 metric series，跨 RPC metric 家族约 `50 K`。
- 若 Redis 调用不需要按业务入口方法排障，继续评估 `caller_method` 是否可在业务自定义指标中降维。
- 本案不建议套用 AMS 案例的 `callee_container` 修复动作，当前证据指向活动新业务维度。

## 0x05 结论（4 月 29 日 0 点本案）

> - 业务：APM 应用 `hpjy-microservices-activities-production`（biz_id `-4228598`）
> - 时间：`2026-04-29 00:00 +0800`
> - 对比窗口：`2026-04-28 23:30 ~ 2026-04-29 00:00` vs `2026-04-29 00:00 ~ 00:30`
> - VM 新增 series 查询：使用 bkop MCP，业务 ID `10`
> - 其他 RPC 指标查询：使用 bkte MCP，业务 ID `-4228598`
> - 基数证据指标：`sum_without_ip_rpc_client_handled_total`
> - 原始 `rpc_client_handled_total` 只用于查询副本数 `R`

### a. TL;DR

- **实际现象**：`00:00` 单分钟新增 `194.5 K` series，`00:01` 仍有 `29.1 K`。
- **额外增量**：`00:00 ~ 00:30` 比前 30 分钟多 `≈ 257.5 K` series。
- **主因**：`activities-60024 / 60015 / 60022` 调向 `hpyd.php.inner.formal`、`amspkg` 后展开。
- **放大器**：主贡献边保留 `callee_container`，包括 `yoyo-inner-*` 与 `ieg-ams-aci-release-*`。
- **注意**：表中 `ΔC` 已包含 `callee_container`，不能直接当作去除该维度的治理收益。

### b. 调用拓扑

```text
[service_name=activity-microservices.activities-60024] (R=60)
├── --> callee_service=hpyd.php.inner.formal
│   ├── ΔC=95
│   ├── driver: user_ext1=act_60024_friend_rank_req
│   └── multiplier: callee_container=yoyo-inner-*
│
└── --> callee_service=trpc.hpjy.activity-microservices.amspkg
    ├── ΔC=59
    ├── driver: user_ext1=act_60024_lottery_req
    └── multiplier: callee_container=ieg-ams-aci-release-*

[service_name=activity-microservices.activities-60015] (R=60)
└── --> callee_service=hpyd.php.inner.formal
    ├── ΔC=86
    ├── driver: caller_method=GetCampActivityOne
    └── multiplier: callee_container=yoyo-inner-*

[service_name=activity-microservices.activities-60022] (R=60)
└── --> callee_service=trpc.hpjy.activity-microservices.amspkg
    ├── ΔC=30
    └── multiplier: callee_container=ieg-ams-aci-release-*

[service_name=activity-microservices.activities-10240] (R=120)
└── --> callee_service=trpc.hpjy.activity-microservices.redis-data
    └── ΔC=37

[service_name=activity-microservices.msgcenter] (R=240)
└── --> callee_service=trpc.hpjy.activity-microservices.activities.10240
    └── ΔC=12  [NEW EDGE]
```

### c. 关键边 series 跳变佐证

| 边 | ΔC | R | `ΔC × R` 上限 | 跨 RPC 家族（×13） | 角色 |
| --- | ---: | ---: | ---: | ---: | --- |
| `60024 -> hpyd.php.inner.formal` | `95` | `60` | `5.7 K` | `74.1 K` | 主贡献边 |
| `60015 -> hpyd.php.inner.formal` | `86` | `60` | `5.2 K` | `67.1 K` | 主贡献边 |
| `10240 -> redis-data` | `37` | `120` | `4.4 K` | `57.7 K` | 次级来源 |
| `60024 -> amspkg` | `59` | `60` | `3.5 K` | `46.0 K` | 主贡献边 |
| `msgcenter -> 10240` | `12` | `240` | `2.9 K` | `37.4 K` | 新入口边 |
| `60022 -> amspkg` | `30` | `60` | `1.8 K` | `23.4 K` | 次级来源 |
| `60009 -> hpyd.php.inner.formal` | `28` | `60` | `1.7 K` | `21.8 K` | 次级来源 |
| `60023 -> amspkg` | `19` | `60` | `1.1 K` | `14.8 K` | 次级来源 |

`ΔC × R × 13` 只表示新增上限。

去除 `callee_container` 的收益需用 `C_with - C_without(callee_container)` 另算。

### d. 总账

| 窗口 | VM 新增 series | 分钟均值 | 峰值 |
| --- | ---: | ---: | ---: |
| `23:30 ~ 00:00` | `32.4 K` | `1.1 K/min` | `1.5 K` |
| `00:00 ~ 00:30` | `289.9 K` | `9.7 K/min` | `194.5 K` |

### e. 缓解动作

- 一期优先评估 `activities-60024` 和 `activities-60015` 的 `callee_container` 去除。
- `activities-60022 / 60009 / 60023` 可作为二期候选。
- `10240 -> redis-data` 需先拆 `user_ext1 / caller_method / callee_method`，不要套用 `callee_container` 修复。

## 0x06 预估（五一 0 点本案）

> - 业务：APM 应用 `hpjy-microservices-activities-production`（biz_id `-4228598`）
> - 时间：`2026-05-01 00:00 +0800`（预估）
> - 基线锚点：`2026-04-29 00:00`，VM 实测 `+257.5 K`
> - 屏蔽生效口径：仅 `callee_container=ignore` 单值
> - 高风险 callee：`{ams,amspkg,amshostpkg,campamspkg}`、`hpyd.php.inner.formal`、`*RecommendLeveledModesForActivity*`

### a. TL;DR

- 五一 0 点 VM 实测预期 `0.75 ~ 2.1 M`，中估 `1.0 ~ 1.5 M`，远低于元旦 `2.39 M`。
- C 类是主要不确定性，单触发 `0.62 M` 跨 4 类。
- B 类 5/1 增量 ≈ 0，业务维度 30 天恒值且无活动期扩容证据。
- A 类实测 `0.082 M`，`10240` 占 78%。
- `60009 / 60015 / 60016` 5/1 减量 ≈ `0.4 M`（4-29 cc 未生效贡献，5/1 ignore 已落地）。
- 名单外 `60022`（cc=471）/ `60024`（cc=173）合计 ≈ `0.47 M`。

### b. 服务分类与拓扑（5/1 视角）

```text
[A] 已 ignore  8 个   CC=1
├── 10240 (R=120) → redis-data        4-29 NEW=41 × 120 = 4.92 K（首发新活动）
├── 10234 (R=120)                     4-29 NEW=8 × 120 = 0.96 K
├── 60025 (R=60)                      静默
├── 10243 (R=120)                     静默
├── 10253 (R=120)                     静默
├── 60009 (R=60)  → hpyd / ams        4-29 cc 未生效贡献 ≈ 5.5 K
├── 60015 (R=60)  → hpyd / amspkg     4-29 cc 未生效贡献 ≈ 10.0 K
└── 60016 (R=60)  → hpyd / amspkg     4-29 cc 未生效贡献 ≈ 16.8 K

[B] 未屏蔽且已稳态扇出 ~400 callee_container  3 个
├── 10135 (R=120) → ams                                          CC=400（4-1~4-28 稳定 300，4-29 微涨）
├── 10129 (R=120) → ams                                          CC=400（4 月中下旬 ramp-up，已完成）
└── 10143 (R=120) → 10143.RecommendLeveledModesForActivity       CC=400（4-24 起稳态）
                                  ⇒ 业务维度全恒值；30 天无活动期扩容证据；5/1 增量 ≈ 0

[C] 未屏蔽 + 当前低基数  10 个   实测低风险（9 个空字符串服务占总存量仅 24%）
├── 10101 (R=120)  CC=2   ΔC=75   仅 ams 边 2 个 container（已部分扇出，0 点可能扩到 400）
├── 10119 (R=120)  CC=空  ΔC=7    完全静默 + msgcenter 未调用 → 5/1 [NEW EDGE]
└── 10127 / 10146 / 10211 / 10238 / 10249 / 10252 (R=120) + 80002 / 80006 (R=60)
                   CC=空          无高风险 callee 调用

[入口]
├── msgcenter (R=240)        18 条已有 callee 边 + 3 条 NEW EDGE（10243 / 10253 / 10119）
└── msgcenter-camp (R=40)    无 NEW EDGE

[名单外隐患]  2 个   不在 5/1 放量名单
├── 60022 (R=60)  → hpyd / amspkg / campamspkg   CC=471   4-29 ΔC=+535（全榜第一），单服务 ≈ 0.42 M
└── 60024 (R=60)  → hpyd / amspkg                CC=173   4-29 ΔC=+52，单服务 ≈ 0.05 M
```

### c. 总账

#### c.1 分类汇总

| 类别 | 服务数 | 单 metric | 跨 4 类（×13） |
| --- | ---: | ---: | ---: |
| A | 8 | ≈ `7 K` | ≈ `0.09 M` |
| B | 3 | `0` | `0` |
| C | 10 | `50 ~ 150 K` | `0.6 ~ 1.9 M` |
| msgcenter | 1 | ≈ `18 K` | ≈ `0.23 M` |
| **5/1 名单内合计** | 21 | **`75 ~ 175 K`** | **`0.92 ~ 2.22 M`** |
| 名单外（`60022` / `60024`） | 2 | + `36 K` | + `0.47 M` |

#### c.2 三情景预估

| 情景 | 假设 | 跨 4 类 | VM 实测预期（×0.8） |
| --- | --- | ---: | ---: |
| 乐观 | 1 个 C 类触发（ΔC=400 × R=120） | `0.94 M` | `0.75 M` |
| 中性 | 2 个 C 类触发（ΔC=800 × R=120） | `1.57 M` | `1.26 M` |
| 悲观 | [1] 3 个 C 类触发（ΔC=1200 × R=120）<br />[2] 名单外 `60022` / `60024` 拉起 | `2.66 M` | `2.13 M` |

元旦斜率回归外推 `3.57 M` 含 `60013` → `campamspkg` cc=400 全展开，五一无对等强度触发点，不采用。

推荐分段算 `0.75 ~ 2.1 M`，中估 `1.0 ~ 1.5 M`。

#### c.3 时序对比（中性场景 vs 历史实测）

- 横轴：`23:40 ~ 00:30`，1 min 一格，纵轴：新增 `series K/min`
- 春节、元旦：bkop VM 实测回放
- 中性：按元旦 0 点形态 × `1.26 / 3.68` 缩放，pre-spike 取 4-29 水位 `≈ 1 K/min`

```text
春节 2026-02-16    Σ ≈ 4.62 M    peak 1422 K
1500 ┤
1250 ┤                                        ╭╮
1000 ┤                                        │ ╰╮
 750 ┤                                        │   ╰╮
 500 ┤                                        │    │
 250 ┤                                        │     ╰╮
   0 ┤───────────────────────────────────────╯        ╰─────────────────────────────────────────────────────
     └──────────────────────────────────────────────────────────────────────────────────────────────────────
      23:40               23:50               00:00               00:10               00:20       00:30

元旦 2026-01-01    Σ ≈ 4.61 M    peak 724 K
 800 ┤
 700 ┤                                        ╭╮
 600 ┤                                        ││
 500 ┤                                        ││
 400 ┤                                        ││
 300 ┤                                        │ ╰╮    ╭╮
 200 ┤                                        │   ╰╮  ││
 100 ┤                                        │     ╰╯  ╰──────╮
   0 ┤───────────────────────────────────────╯                  ╰───────────────────────────────────────────
     └──────────────────────────────────────────────────────────────────────────────────────────────────────
      23:40               23:50               00:00               00:10               00:20       00:30

五一中性预估       Σ ≈ 1.28 M    peak 350 K
 400 ┤
 300 ┤                                        ╭╮
 200 ┤                                        │ ╰╮
 100 ┤                                        │   ╰╮
  50 ┤                                        │     ╰╮
   0 ┤───────────────────────────────────────╯        ╰─────────────────────────────────────────────────────
     └──────────────────────────────────────────────────────────────────────────────────────────────────────
      23:40               23:50               00:00               00:10               00:20       00:30
```

读图要点：

- 单分钟峰值：春节 `1422 K`，元旦 `724 K`，中性预估 `≈ 350 K`，`5 min` 内回落到 `≤ 50 K`
- 元旦 `00:04` 次峰 `315 K` 来自 `60013 → hpyd` 二次扇出，五一无对应触发点，不复现
- `23:40 ~ 00:30` 总量：春节 / 元旦 `≈ 4.6 M`，五一中性预估 `≈ 1.3 M`，约为前者 `1/4`

## 0x07 结论（4 月 30 日 0 点本案）

> - 业务：APM 应用 `hpjy-microservices-activities-production`（biz_id `-4228598`）
> - 时间：`2026-04-30 00:00 +0800`
> - 对比窗口：`2026-04-29 23:30 ~ 2026-04-30 00:00` vs `2026-04-30 00:00 ~ 00:30`
> - VM 新增 series 查询：使用 bkop MCP，业务 ID `10`
> - 其他 RPC 指标查询：使用 bkte MCP，业务 ID `-4228598`
> - 基数证据指标：`sum_without_ip_rpc_client_handled_total`
> - 原始 `rpc_client_handled_total` 只用于查询副本数 `R`

### a. TL;DR

- **实际现象**：`00:00` 单分钟新增 `226.4 K` series，`00:01` 即回落至 `4.6 K`，`5 min` 内基本归位。
- **基线水位**：`23:00 ~ 23:59` 平均 `1.0 K/min`，`00:00 ~ 00:09` 累计 `242 K`。
- **形态特征**：分散型尖峰，无 NEW SERVICE / NEW EDGE 大爆发，`(service_name, callee_service)` 边总数稳定在 `180 ~ 194` 之间。
- **主因**：`[B]` 类稳态扇出边的 `callee_container` 偶发再现，叠加少量业务维度新值与若干瞬时 `callee_method` 扇出。
- **主贡献边**：`10135 → ams`、`10143 → RecommendLeveledModesForActivity`、`10129 → ams`。
- **量级定位**：本次 `226.4 K` 与 `0x05` 的 `4-29` 案 `194.5 K` 同量级，远低于元旦 `724 K` 与五一中性预估 `350 K`。
- **场景定性**：属于「无活动放量日」基线尖峰，非异常事件。

### b. 调用拓扑

按驱动机制分三类。

`[A]` 业务维度新值上线（持久新增）：

```text
├── activities-60022 (R=60)  → redis-data    ΔC=+19  driver: user_ext1=act_60022_query_winner_req（新业务动作）
├── activities-10243 (R=120) → redis-data    ΔC=+17  driver: user_ext1（具体新值未单独拆解）
└── activities-10240 (R=120) → msgcenter     ΔC=+14  driver: callee_method=UpdateRedpointReissue（新方法上线，0 点前未上报）
```

`[B]` 高基数 `callee_container` 盲区命中（持久新增 ≈ 5m ΔC，cc 命中后仍持续上报）：

```text
├── activities-10135 (R=120) → ams                                       ΔC=+32  driver: callee_container 流量增大命中更多 pod
├── activities-10143 (R=120) → 10143.RecommendLeveledModesForActivity    ΔC=+30  driver: callee_container 同上
└── activities-10129 (R=120) → ams                                       ΔC=+6 ~ +30 波动  driver: callee_container 同上
```

`[C]` 现有 `callee_method` 子组合瞬时扇出（5m ΔC 包含 `00:01` 单分钟峰值，持久 ΔC 显著小于此值）：

```text
├── activities-10127 (R=120) → msgcenter.forward     5m ΔC=+13
├── activities-10127 (R=120) → msgcenter             5m ΔC=+12
├── activities-10249 (R=120) → msgcenter             5m ΔC=+11
├── activities-10238 (R=120) → msgcenter             5m ΔC=+8
├── activities-10146 (R=120) → msgcenter             5m ΔC=+7   持久 ΔC=+3   driver: callee_method=UpdateRedpointReissue (4→6) + NotifyActivity (4→5)
├── activities-10050 (R=120) → msgcenter             5m ΔC=+7
└── activities-10101 (R=120) → msgcenter             5m ΔC=+2
```

```text
[D] 其余小幅扩展（5m ΔC ≤ 6）
├── activities-10101 (R=120) → redis-data    ΔC=+6
├── activities-10240 (R=120) → redis-data    ΔC=+6
├── activities-10237 (R=120) → redis-data    ΔC=+4
├── activities-{60024,60016} (R=60) → redis-data  ΔC=+3
└── 其他 ≈ 12 条 ΔC ≤ 3 的边
```

图例：

- `ΔC` 计算口径：用 `count by(service_name, callee_service)(sum_over_time([5m]))` 在 `00:05` 与 `23:55` 两个端点对比。
- 5m 窗口包含 `00:01` 单分钟瞬时偶发，等同于 VM 「累计新增」视角，c.3 节给出 `[C]` 类的持久 ΔC 校准方法。
- `[B]` 类沿用 `0x06 b` 节定义：业务维度恒值且 `30` 天无活动期扩容证据的高基数 `callee_container` 边。
- `60022 / 60024 / 60023` 调向 `amspkg / hpyd / campamspkg` 等 `0x05 b` 主贡献边今晚处于 series 衰减状态，未贡献新增。

### c. 关键边 series 跳变佐证

#### c.1 边总数随时间稳定，无 NEW EDGE 爆发

```promql
count(count by (service_name, callee_service) (
  sum_over_time(sum_without_ip_rpc_client_handled_total[1m])
))
```

| 时刻 | 23:56 | 23:57 | 23:58 | 23:59 | 00:00 | 00:01 | 00:02 | 00:03 | 00:04 | 00:05 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 边总数 | 193 | 192 | 194 | 190 | 192 | 193 | 181 | 186 | 183 | 184 |

> 0 点前后边集合几乎不变，226.4 K 新增不来自新边。

#### c.2 `[B]` 类稳态边 `callee_container` 偶发再现

以 `10135 → ams` 为样本：

```promql
count by (callee_container) (
  sum_over_time(sum_without_ip_rpc_client_handled_total{
    service_name="activity-microservices.activities-10135",
    callee_service="trpc.hpjy.activity-microservices.ams"
  }[1m])
)
```

| 时刻 | 23:56 | 23:57 | 23:58 | 23:59 | 00:00 | 00:01 | 00:02 | 00:03 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 min 内 distinct container | 96 | 115 | 83 | 46 | 81 | 127 | 117 | 109 |

读法：

- 30 min 累积 `360` 个 container（接近全集 `≈ 400`），单 1 min 仅 `46 ~ 127`。
- `23:59` 谷底 `46` → `00:01` 峰值 `127`，差值 `+81` 即 0 点流量增大后被命中的 container。
- 这些 container 在 VM 视角属于「过期再创建」，每次都计入 `vm_new_timeseries_created_total`。

#### c.3 `[C]` 类反向边持久 vs 瞬时校准

以 `10146 → msgcenter` 为样本（用户重点质疑边）。

边总 series 1 min 时序：

| 时刻 | 23:50 | 23:55 | 23:59 | `00:00` | `00:01` | `00:02` | `00:03` | `00:04` | `00:05` | `00:09` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 min series | `9` | `9` | `9` | `9` | `16` | `13` | `13` | `12` | `12` | `12` |

按 `callee_method` 拆解（5 min 窗口）：

| `callee_method` | `23:50 ~ 23:55` | `23:55 ~ 00:00` | `00:00 ~ 00:05` |
| --- | ---: | ---: | ---: |
| `UpdateRedpointReissue` | `4` | `10` | `6` |
| `NotifyActivity` | `4` | `5` | `5` |
| `CallOther` | `1` | `1` | `1` |
| 合计 | `9` | `16` | `12` |

读法：

- 5m 累计 ΔC = `12 − 9 = +3`，跟 1 min 稳态对比一致，是真实持久增量。
- `00:01` 单分钟峰值 `16` 来自瞬时新增 `user_ext1 = act_10146_lottery_req` / `act_10146_get_code_cfg_req`，下一分钟即消失。
- 之前用 `count[1m] − count[1m] offset 5m` 得到的 `+7` 把瞬时峰值算入 ΔC，会高估 `[C]` 类反向边的持久增量。
- VM 视角的 `vm_new_timeseries_created_total` 会同时累计瞬时与持久部分，因此 `00:01` 单分钟的 `226 K` 既包含 `[A] / [B]` 的持久新值，也包含 `[C]` 的瞬时偶发。

### d. 总账

VM 实测：

```promql
sum(increase(bkmonitor:vm_new_timeseries_created_total{
  bk_monitor_name="monitor-hpjyapm-servicemonitor"
}[1m]))
```

| 窗口 | 总量 | 分钟均值 | 单分钟峰值 |
| --- | ---: | ---: | ---: |
| `23:00 ~ 23:59` | `60.8 K` | `1.0 K/min` | `1.5 K` |
| `00:00 ~ 00:09` | `242.2 K` | `26.9 K/min` | `226.4 K` |
| `00:00 ~ 00:17` | `252.3 K` | — | — |

按类别聚合 ΔC × R 估算：

- 单 metric 上限 = `Σ_{服务∈类别}(Σ(出边 5m ΔC) × R)`
- 跨 4 类 RPC metric 家族 = 单 metric 上限 × `13`
- 类别沿用 b 节定义

| 类别 | driver | 服务数 | 单 metric | 跨 4 类（×13） | 主要服务 |
| --- | --- | ---: | ---: | ---: | --- |
| `[A]` 业务新值 | `user_ext1` / `callee_method` 上线 | `3` | `≈ 5.6 K` | `≈ 72 K` | `activities-{10240,10243,60022}` |
| `[B]` cc 盲区 | `callee_container` 流量增大命中更多 pod | `2` | `≈ 8.3 K` | `≈ 108 K` | `activities-{10143,10135}` |
| `[C]` method 瞬时扇出 | `callee_method=UpdateRedpointReissue` 在 `00:01` 短暂展开 | `6` | `≈ 9.1 K` | `≈ 119 K` | `activities-{10127,10249,10101,10238,10146,10050}` |
| `[D]` 其余 | 综合，单服务 ΔC ≤ `5` | `≈ 13` | `≈ 3.7 K` | `≈ 48 K` | `msgcenter` 出边 + 多个小活动服务 |
| **合计** | — | `≈ 24` | **`≈ 27 K`** | **`≈ 347 K`** | — |

口径一致性：

- 跨 4 类上限 `347 K` 高于 VM 实测 `226.4 K`，差额来自 ΔC × R 默认假设 series 在每个副本上都展开，实际只覆盖部分。
- `[C]` 类按 5m ΔC 计入合计，其中含 `00:01` 单分钟瞬时偶发。
- 若全部按持久 ΔC 校准（如 `10146` 由 `+9` 降为 `+3`），`[C]` 类跨 4 类可压缩至 `≈ 40 ~ 50 K`，总账下调约 `70 ~ 80 K`，更贴近 VM 实测。
- 不写成「治理收益 100 %」，仅作为风险上限参考。

## 0x08 结论（五一 0 点本案）

> - 业务：APM 应用 `hpjy-microservices-activities-production`（biz_id `-4228598`）
> - 时间：`2026-05-01 00:00 +0800`
> - 对比窗口：`23:30 ~ 00:00`（before）vs `00:00 ~ 00:30`（after）
> - 边级窗口：`23:50 ~ 00:00` vs `00:00 ~ 00:10`，各 `[10m]`
> - VM 新增 series 用 bkop MCP，业务 ID `10`
> - 其他 RPC 指标用 bkte MCP，业务 ID `-4228598`
> - 基数证据指标：`sum_without_ip_rpc_client_handled_total`

### a. TL;DR

- **峰值**：`00:00` 单分钟新增 `408.5 K`，`5 min` 内回落到 `≤ 2 K/min`。
- **总量**：`23:30 ~ 00:00` 基线 `12.6 K`，`00:00 ~ 00:30` 累计 `≈ 473 K`，**额外新增 `≈ 460 K`**。
- **vs 预估**：仅为 `0x06` 中性档 `1.26 M` 的 `37%`，乐观档 `0.75 M` 的 `61%`。
- **形态**：`[NEW EDGE]` 仅 `6` 条，无大规模全新边爆发，总边数 `185 ~ 198` 区间，`00:01` 短暂达峰 `198`。
- **预估命中**：`10119` 命中 `[NEW EDGE]` 预测，`[B]` 类无 cc 跳变（`ΔC=+25` 仅来自常规波动），`[名单外隐患]` `60022 / 60024` 未拉起。
- **A 类规避**：8 服务单指标合计 `≈ 4.5 K`，5/1 高 cc 新边只有 `60015 → hpyd ΔC=+1`，显式规避 `≈ 2.3 K` 多指标（详见 `d`）。

### b. 调用拓扑

按 `0x06 b` 服务名单（caller 视角）分类。

- 重点边（`ΔC ≥ 3` 或 `[NEW EDGE]` 或调向高 cc callee）逐条列出，其余按 callee 合并为尾部一行。
- 高 cc callee 集：`ams` / `amspkg` / `amshostpkg` / `campamspkg` / `hpyd.php.inner.formal` / `10143.RecommendLevel...`。
- `callee_service` 省略 `trpc.hpjy.activity-microservices.` 前缀。

`[A]` 已 ignore（`0x06` 名单 8 个，本次 7 个触发，`60009` 静默）：

```text
├── activities-10243 (R=120)                     → redis-data             ΔC=+14  driver: user_ext1=act_10243_*
├── activities-10240 (R=120)                     → msgcenter              ΔC=+9
├── activities-10240 (R=120)                     → redis-data             ΔC=+3
├── activities-10243 (R=120)                     → msgcenter.forward      ΔC=+2  [NEW EDGE]
├── activities-60015 (R=60)                      → hpyd.php.inner.formal  ΔC=+1  高 cc callee
├── 10234 / 10253 (R=120) + 60016 / 60025 (R=60) → redis-data             ΔC=+7
└── 10234 / 10253 / 10243 (R=120)                → msgcenter              ΔC=+4
```

`[B]` 未屏蔽 + 稳态扇出 ~400 cc（`0x06` 名单 3 个，`10129 / 10135 / 10143`）：

```text
├── activities-10129 (R=120) → ams                ΔC=+9  高 cc callee
├── activities-10129 (R=120) → trpc.http.pandora  ΔC=+4
├── activities-10143 (R=120) → redis-data         ΔC=+3
├── activities-10135 (R=120) → ams                ΔC=+2  高 cc callee
├── 10129 / 10135 (R=120)    → redis-data         ΔC=+4
└── 10129 / 10143 (R=120)    → msgcenter          ΔC=+3
```

`[B]` 业务维度恒值，cc 集合接近全集，无 `ΔC=+30` 量级跳变。

`[C]` 未屏蔽 + 低基数（`0x06` 名单 10 个，本次 9 个触发，`80006` 静默）：

```text
├── activities-10119 (R=120)                              → redis-data              ΔC=+31  driver: user_ext1=act_10119_*
├── activities-10127 (R=120)                              → msgcenter               ΔC=+14
├── activities-10127 (R=120)                              → msgcenter.forward       ΔC=+14
├── activities-10249 (R=120)                              → msgcenter               ΔC=+11
├── activities-{10146,10211,10238} (R=120)                → msgcenter               ΔC=+8
├── activities-10252 (R=120)                              → redis-data              ΔC=+8
├── activities-10119 (R=120)                              → msgcenter.forward       ΔC=+6  [NEW EDGE]
├── activities-10119 (R=120)                              → msgcenter               ΔC=+4  [NEW EDGE]
├── activities-80002 (R=60)                               → redis-data              ΔC=+4
├── 10101 / 10127 / 10146 / 10211 / 10238 / 10249 (R=120) → redis-data              ΔC=+11
├── 10101 (R=120) + 80002 (R=60)                          → msgcenter               ΔC=+2
└── 80002 (R=60)                                          → trpc.hpjytv.coin.inner  ΔC=+1
```

`[C]` 无高 cc callee，`10119` 命中 `0x06` 预估的 `[NEW EDGE]`，`10101` 未触达 `cc=400`。

入口（`0x06` 名单 2 个，全部触发）：

```text
├── msgcenter (R=240)     → producer_wx                           ΔC=+12
├── msgcenter (R=240)     → activities.10119                      ΔC=+11  [NEW EDGE]  10119 入口首次调用
├── msgcenter (R=240)     → producer_sq                           ΔC=+9
├── msgcenter (R=240)     → activities.10239                      ΔC=+6
├── msgcenter (R=240)     → activities.{10050,10230}              ΔC=+5
├── msgcenter (R=240)     → activities.{10156,10243,10252}        ΔC=+4
├── msgcenter (R=240)     → trpc.cj.trpc2s.activitysvr            ΔC=+2
├── msgcenter-camp (R=40) → activities.60016                      ΔC=+2
├── msgcenter (R=240)     → activities.{10101,10231,10240,10253}  ΔC=+1
└── msgcenter-camp (R=40) → activities.{60009,60024}              ΔC=+1
```

入口无高 cc callee，新边 `msgcenter → activities.10119` 与 `0x06` 预估一致。

`[名单外隐患]`（`0x06` 名单 2 个，`60022 / 60024`）：

```text
├── activities-60024 (R=60) → redis-data             ΔC=+8
├── activities-60022 (R=60) → redis-data             ΔC=+5
└── activities-60024 (R=60) → hpyd.php.inner.formal  ΔC=+3  [NEW EDGE]  高 cc callee，yoyo-inner-* 仅命中 3 个 pod
```

`60024 → hpyd` 仅命中 `3` 个 pod，远低于全集 `≈ 60`，未触发悲观档预估。

`[名单外新增]`（`0x06` 未列入但 5/1 实际有增长，`6` 个 caller）：

```text
├── activities-10239 (R=120)              → redis-data             ΔC=+16  driver: user_ext1=act_10239_*
├── activities-60023 (R=60)               → hpyd.php.inner.formal  ΔC=+6  高 cc callee
├── activities-10050 (R=120)              → msgcenter              ΔC=+3
├── activities-10239 (R=120)              → msgcenter.forward      ΔC=+1  [NEW EDGE]
├── 10050 / 10156 / 10230 / 10231 (R=120) → redis-data             ΔC=+8
├── 10156 / 10230 / 10239 (R=120)         → msgcenter              ΔC=+3
└── 10050 / 10156 / 10231 (R=120)         → msgcenter.forward      ΔC=+3
```

`10239` 量级与 `0x06 [C]` 类持平，候选下一轮纳入风险名单。

### c. 总账

#### c.1 vs `0x06` 三档预估

| 情景 | `0x06` VM 预期 | 5/1 实测 | 实测 / 预期 |
| --- | ---: | ---: | ---: |
| 乐观（1 个 C 类触发） | `0.75 M` | `≈ 0.46 M` | **`61%`** |
| 中性（2 个 C 类触发） | `1.26 M` | `≈ 0.46 M` | `37%` |
| 悲观（3 个 C 类 + 名单外拉起） | `2.13 M` | `≈ 0.46 M` | `22%` |

实测落在乐观档之下，主要由 3 个偏离项叠加：

- `[名单外隐患]` `60022 / 60024` 未拉起活动放量，`60024 → hpyd` 仅命中 `3` 个 pod。
- `[B]` 类 `10135 / 10129 / 10143` 业务维度恒值，cc 集合无阶跃扩张。
- `[C]` 类仅 `10119` 触发全新边，未扇出到 `cc=400` 量级。

#### c.2 类别汇总

| 类别 | 服务数 | ΔC | 单指标 | 多指标合计 |
| --- | ---: | ---: | ---: | ---: |
| `[A]` | 7 | +40 | `≈ 4.5 K` | `≈ 58.5 K` |
| `[B]` | 3 | +25 | `≈ 3.0 K` | `≈ 39.0 K` |
| `[C]` | 9 | +130 | `≈ 15.2 K` | `≈ 198.1 K` |
| 入口 | 2 | +70 | `≈ 16.0 K` | `≈ 208.0 K` |
| `[名单外隐患]` | 2 | +16 | `≈ 1.0 K` | `≈ 12.5 K` |
| `[名单外新增]` | 6 | +40 | `≈ 4.4 K` | `≈ 57.7 K` |
| **合计** | **29** | **+321** | **`≈ 44.1 K`** | **`≈ 573.8 K`** |

多指标合计 = 单指标 × `13`，覆盖 `total` / `count` / `sum` 与 `histogram` 的 `10` 个 bucket。

`573.8 K` 是 `ΔC × R` 的上限，假设 series 在每个 caller 副本完整展开，VM 实测额外 `460 K`，差额来自部分副本未触达。

### d. A 类规避收益

A 类 8 服务的 `callee_container` 已 ignore 为单值，5/1 0 点显式可计算的规避只有一条高 cc 新边。

| 高 cc 边 | R | ΔC | CC | 单指标 | 多指标合计（×13） |
| --- | ---: | ---: | ---: | ---: | ---: |
| `60015 → hpyd.php.inner.formal` | `60` | `+1` | `3` | `0.18 K` | `2.34 K` |

公式 `avoidance = ΔC × R × CC`，`CC` 取 5/1 当晚同窗口实际枚举值，与 `60024 → hpyd ΔC=+3 [NEW EDGE]` 的 `yoyo-inner-* 命中 3 个 pod` 同尺度。

显式部分约占 5/1 实测额外 `460 K` 的 `0.5%`，其余 7 服务出边全部落在 `redis-data` / `msgcenter` / `msgcenter.forward`，不计入。

隐性部分指已有高 cc 边的 `callee_container` 集合扩张，ignore 生效后无法直接量化。

按 `0x07 c.2` `10135 → ams` `1 min` cc 集 `46 → 127` 同等扩张投影，多指标合计上限 `30 ~ 90 K`，约占 `7 ~ 20%`。

旧版 `4-29 cc 未生效 32.3 K` 推算的 `0.42 M` 不再使用：该基线把稳态 cc 集合算成 0 点新增，与 5/1 单点峰值不同义。

## 0x09 预估（8 月 8 日空投节 0 点本案）

> - 状态：事前预测，数据截止 `2026-08-05`
> - 活动范围：`25` 个活动服务及 `msgcenter`、`eventcenter`、`retrycenter`
> - QPM 假设：与春节相同，约为五一的 `1.264` 倍
> - 当前窗口：最近 `30 min`
> - 历史集合：最近 `30 d`
> - 预热率：`C_active / (C_active + C_dormant)`
> - 容器维度：全部活动服务均为 `callee_container=ignore`

### a. TL;DR

- 当前 series 理论展开量为 `4.308 M`，整体预热率为 `48.5%`。
- 历史出现但当前未出现的组合，加上 `4` 个未见服务的代理值，潜在新增上限为 `4.574 M`。
- 主要增量预计来自 `msgcenter → activities` 入口和 `activities → redis-data`。
- AMS、hpyd、Recommend 等历史高风险接口已去除容器维度。
- 单分钟峰值预计为 `0.8 M～1.5 M`，中性值为 `1.1 M`。
- 前三分钟累计预计为 `1.0 M～3.0 M`，中性值为 `1.7 M`。
- 前 `30` 分钟累计预计为 `1.2 M～3.8 M`，中性值为 `2.2 M`。

容量按 `1.7 M/min`、`4.1 M/3min`、`5.5 M/30min` 预留。

### b. 服务分类与预期拓扑

```text
msgcenter
└── activities.<id>
    ├── redis-data                     业务维度扩展的主要来源
    ├── msgcenter / msgcenter.forward  消息回调
    └── AMS / hpyd / Recommend         历史高风险，本次已去除容器维度
```

活动服务按预热率分类：

```text
[A] 预热率 ≥ 70%，4 个
├── 10257 / 10259 / 10261  (R=240)
└── 60038                  (R=60)

[B] 预热率 40%～70%，13 个
├── R=240
│   └── 10135 / 10211 / 10258 / 10267 / 10268
│       / 10273 / 10276 / 10282 / 60037
└── R=60
    └── 60009 / 60030 / 80006 / 80010

[C] 预热率 < 40%，4 个
└── 10119 / 10192 / 10230 / 10279  (R=240)

[D] 最近 30 天未出现，4 个
└── 10148 / 10214 / 10275 / 10277
    └── 按 C=52、R=240 估算

[公共服务]
├── msgcenter    R=480
├── eventcenter  R=1
└── retrycenter  当前未上报，按 R=240 估算
```

`C=52`、`R=240` 是代理值，不是 `[D]` 类服务的实测值。

活动入口没有完全预热：

| 调用 | 当前组合 | 暂未出现组合 | 预热率 |
| --- | ---: | ---: | ---: |
| `msgcenter → activities` | `126` | `187` | `40.3%` |
| `msgcenter → producer_sq` | `57` | `56` | `50.4%` |
| `msgcenter → producer_wx` | `56` | `61` | `47.9%` |
| `msgcenter → trpc2s.activitysvr` | `11` | `25` | `30.6%` |

Redis 调用是活动服务的主要候选增量：

| 调用边 | 当前组合 | 暂未出现组合 | 预热率 |
| --- | ---: | ---: | ---: |
| `10273 → redis-data` | `138` | `61` | `69.3%` |
| `10258 → redis-data` | `78` | `28` | `73.6%` |
| `10267 → redis-data` | `53` | `52` | `50.5%` |
| `10192 → redis-data` | `10` | `38` | `20.8%` |
| `10230 → redis-data` | `7` | `22` | `24.1%` |

AMS、hpyd、Recommend 等接口仍需观察，但其 `callee_container` 已为 `ignore`，不会产生春节时的容器倍数。

### c. 总账

表中展开量已乘入副本数和 RPC metric 家族系数 `13`：

| 分类 | 当前组合 | 暂未出现／估算组合 | 当前展开量 | 潜在新增上限 | 预热率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `[A]` 高预热 | `182` | `33` | `0.409 M` | `0.070 M` | `85.3%` |
| `[B]` 部分预热 | `905` | `560` | `2.211 M` | `1.340 M` | `62.3%` |
| `[C]` 低预热 | `41` | `144` | `0.128 M` | `0.449 M` | `22.2%` |
| `[D]` 未见服务 | `0` | `208` | `0` | `0.649 M` | `0%` |
| `msgcenter` | `250` | `329` | `1.560 M` | `2.053 M` | `43.2%` |
| `eventcenter` | `50` | `33` | `< 0.001 M` | `< 0.001 M` | `60.2%` |
| `retrycenter` | `0` | `4` | `0` | `0.012 M` | `0%` |
| **合计** | **`1,428`** | **`1,311`** | **`4.308 M`** | **`4.574 M`** | **`48.5%`** |

`4.574 M` 是组合覆盖所有副本后的上限，不是 VM 必然新增量。

| 情景 | 条件 | 单分钟峰值 | 前三分钟 | 前 30 分钟 |
| --- | --- | ---: | ---: | ---: |
| 乐观 | 少量历史组合恢复，接近五一形态 | `0.8 M` | `1.0 M` | `1.2 M` |
| 中性 | 入口恢复，部分 Redis 组合重新出现 | `1.1 M` | `1.7 M` | `2.2 M` |
| 悲观 | 未见服务及大部分历史组合同时出现 | `1.5 M` | `3.0 M` | `3.8 M` |
| 容量预留 | 新业务维度超出最近 `30 d` 的历史范围 | `1.7 M` | `4.1 M` | `5.5 M` |

## 0x10 结论（8 月 8 日空投节 0 点本案）

> - 业务：APM 应用 `hpjy-microservices-activities-production`（biz_id `-4228598`）
> - 时间：`2026-08-08 00:00 +0800`
> - 对比窗口：`23:30～00:00`（before）vs `00:00～00:30`（after）
> - 边级窗口：`23:50～00:00` vs `00:00～00:10`，各 `[10m]`
> - VM 新增 series 用 bkop MCP，业务 ID `10`
> - 其他 RPC 指标用 bkte MCP，业务 ID `-4228598`
> - 基数证据指标：`sum_without_ip_rpc_client_handled_total`

### a. TL;DR

- **峰值**：`00:00` 单分钟新增 `1.144 M`；`00:10` 出现 `384.4 K` 的第二峰。
- **总量**：before 基线 `15.2 K`，after 累计 `2.377 M`，额外新增 `2.361 M`。
- **vs 预估**：单分钟、前三分钟和前 `30` 分钟均落入 `0x09` 区间，与中性值偏差均小于 `10%`。
- **QPM**：峰值 `1.098 B`，是春节的 `1.115` 倍、五一的 `1.409` 倍。
- **形态**：出现 `17` 条 `[NEW EDGE]`；边数从 `139` 增加到 `152`，期间峰值为 `156`。
- **增量来源**：新增组合共 `812` 个，其中历史组合重现 `509` 个，最近 `30 d` 首次出现 `303` 个。
- **容器维度**：`25` 个活动服务均为 `callee_container=ignore`，历史 pod 扇出没有复现。

本次 QPM 高于春节，但 VM 单分钟峰值只有春节的 `80.4%`。QPM 仍不能直接换算为新增 series。

### b. 调用拓扑

`25` 个活动服务全部上报：

- `20` 个服务为 `R=240`。
- `60009`、`60030`、`60038`、`80006`、`80010` 为 `R=60`。
- `msgcenter` 为 `R=480`，`eventcenter` 为 `R=1`。
- `retrycenter` 没有上报。

主要组合增量：

```text
├── activities-10148 → redis-data             ΔC=+65  [D]
├── activities-10214 → redis-data             ΔC=+65  [D]
├── msgcenter         → producer_sq           ΔC=+64  入口公共输出
├── activities-10119 → redis-data             ΔC=+47  [C]
├── activities-10275 → redis-data             ΔC=+44  [D]
├── activities-10257 → redis-data             ΔC=+42  [A]
├── activities-10258 → redis-data             ΔC=+32  [B]
├── activities-10258 → msgcenter.forward      ΔC=+28  [B]
├── activities-10277 → redis-data             ΔC=+28  [D]
└── activities-10279 → redis-data             ΔC=+20  [C]
```

`[D]` 类事前未见服务全部触发：

```text
├── activities-10148 (R=240)
│   ├── redis-data          ΔC=+65
│   ├── msgcenter           ΔC=+8   [NEW EDGE]
│   ├── msgcenter.forward   ΔC=+4   [NEW EDGE]
│   └── ams                 ΔC=+1   [NEW EDGE]
├── activities-10214 (R=240)
│   ├── redis-data          ΔC=+65
│   ├── msgcenter.forward   ΔC=+9   [NEW EDGE]
│   ├── msgcenter           ΔC=+6   [NEW EDGE]
│   └── ams                 ΔC=+1   [NEW EDGE]
├── activities-10275 (R=240)
│   ├── redis-data          ΔC=+44
│   ├── msgcenter.forward   ΔC=+11  [NEW EDGE]
│   └── msgcenter           ΔC=+2   [NEW EDGE]
└── activities-10277 (R=240)
    └── redis-data          ΔC=+28
```

入口 `msgcenter`：

```text
├── producer_sq          ΔC=+64
├── producer_wx          ΔC=+20
├── activities.10148     ΔC=+17  [NEW EDGE]
├── activities.10119     ΔC=+15  [NEW EDGE]
├── activities.10214     ΔC=+13  [NEW EDGE]
└── activities.10275     ΔC=+10  [NEW EDGE]
```

历史高风险接口：

| 调用边 | ΔC | 边状态 |
| --- | ---: | --- |
| `60030 → hpyd` | `+5` | 已有边 |
| `60037 → hpyd` | `+3` | `[NEW EDGE]` |
| `10192 → Recommend` | `+3` | 已有边 |
| `60038 → hpyd` | `+1` | 已有边 |
| `10148 → ams` | `+1` | `[NEW EDGE]` |
| `10214 → ams` | `+1` | `[NEW EDGE]` |

这些接口的增量均不超过 `5` 个组合。`callee_container=ignore` 生效后，AMS、hpyd、Recommend 没有按 pod 数放大。

### c. 总账

#### c.1 vs `0x09` 三档预估

| 指标 | `0x09` 区间 | 中性值 | 实测 | 实测 / 中性 |
| --- | ---: | ---: | ---: | ---: |
| 单分钟峰值 | `0.8 M～1.5 M` | `1.1 M` | `1.144 M` | `104.0%` |
| 前三分钟累计 | `1.0 M～3.0 M` | `1.7 M` | `1.568 M` | `92.2%` |
| 前 30 分钟累计 | `1.2 M～3.8 M` | `2.2 M` | `2.377 M` | `108.0%` |

三项实测均落在预测区间内。容量预留分别覆盖实测峰值的 `1.49` 倍、`2.61` 倍和 `2.31` 倍。

#### c.2 类别汇总

| 类别 | ΔC | 多指标上限 | 占比 |
| --- | ---: | ---: | ---: |
| `[A]` 高预热 | `+61` | `159.9 K` | `5.4%` |
| `[B]` 部分预热 | `+226` | `590.5 K` | `19.9%` |
| `[C]` 低预热 | `+86` | `268.3 K` | `9.0%` |
| `[D]` 事前未见 | `+245` | `764.4 K` | `25.7%` |
| `msgcenter` | `+190` | `1.186 M` | `39.9%` |
| `eventcenter` | `+4` | `52` | `< 0.1%` |
| `retrycenter` | `0` | `0` | `0%` |
| **合计** | **`+812`** | **`2.969 M`** | **`100%`** |

多指标上限 = `ΔC × R × 13`，覆盖 `total`、`count`、`sum` 与 histogram 的 `10` 个 bucket。

`2.969 M` 是所有组合在副本上完整展开的上限。VM 额外新增为 `2.361 M`，相当于上限的 `79.5%`。

#### c.3 潜伏组合与首次出现组合

| 来源 | 组合数 | 组合占比 | 多指标上限 | 上限占比 |
| --- | ---: | ---: | ---: | ---: |
| 最近 `30 d` 出现、活动前 `10 min` 未出现 | `509` | `62.7%` | `1.718 M` | `57.9%` |
| 最近 `30 d` 首次出现 | `303` | `37.3%` | `1.251 M` | `42.1%` |
| **合计** | **`812`** | **`100%`** | **`2.969 M`** | **`100%`** |

潜伏组合重建仍是主要来源。首次出现组合占比为 `37.3%`，说明只按历史组合估算会漏掉约四成加权上限。

#### c.4 与过往活动对比

| 节点 | QPM 峰值 | 单分钟峰值 | 前三分钟 | 前 30 分钟 |
| --- | ---: | ---: | ---: | ---: |
| 春节 | `985.3 M` | `1.422 M` | `3.415 M` | `4.59 M` |
| 五一 | `779.6 M` | `408.5 K` | `438.7 K` | `473 K` |
| 空投节 | `1.098 B` | `1.144 M` | `1.568 M` | `2.377 M` |

空投节 QPM 比春节高 `11.5%`，但前三分钟和前 `30` 分钟新增量分别只有春节的 `45.9%` 和 `51.8%`。容器维度去除后，峰后累计明显降低。

### d. 未见服务代理校验

| 服务 | 事前代理 C | 实测 ΔC | 偏差 | 事前代理 R | 实测 R |
| --- | ---: | ---: | ---: | ---: | ---: |
| `10148` | `52` | `78` | `+50.0%` | `240` | `240` |
| `10214` | `52` | `81` | `+55.8%` | `240` | `240` |
| `10275` | `52` | `57` | `+9.6%` | `240` | `240` |
| `10277` | `52` | `29` | `-44.2%` | `240` | `240` |
| **合计** | **`208`** | **`245`** | **`+17.8%`** |  |  |

副本数众数 `R=240` 命中。组合数代理池低估了 `17.8%`，后续同类活动可将未见服务的组合代理上调约 `20%`。

`[D]` 类服务在预测后至活动前已出现部分组合，因此没有以完全冷启动的形态进入 `00:00`。事前按非零值纳入仍是必要的。

### e. 容器维度收益与第二峰

全部活动服务的 `callee_container` 只有 `ignore`。本次观察到的高风险接口组合增量为 `+14`，没有 pod 维度倍数。

`00:10` 的 VM 第二峰为 `384.4 K/min`。同一分钟业务指标出现 `67` 个新组合，按副本和 `13` 个 metric family 展开约为 `213 K`，只能覆盖部分 VM 增量。

现有证据不能把第二峰归因到单条 Redis 或高风险边。后续复盘需要补充 `00:09～00:11` 的实例触达分布和业务调度记录。
