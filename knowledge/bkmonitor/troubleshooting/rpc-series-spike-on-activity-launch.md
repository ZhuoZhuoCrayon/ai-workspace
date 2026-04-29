---
title: 0 点活动上线导致 RPC 指标 series 暴涨
tags: [apm, rpc, cardinality, series-spike, callee-container, sum-without-ip, fan-out]
description: 通过 ΔC 边对比、维度拆解与 VM 新增 series 验证，定位活动上线引发的 RPC 指标 series 暴涨；区分业务新值驱动与高基数扇出乘子。
created: 2026-04-25
updated: 2026-04-29
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
