---
title: 0 点活动上线导致 RPC 指标 series 暴涨
tags: [apm, rpc, cardinality, series-spike, callee-container, sum-without-ip, fan-out]
description: 通过 ΔC 边对比 + 维度拆解 + 新值/fan-out 乘子辨析，定位活动上线引发的 series 暴涨。callee_container 是 800 倍 fan-out 乘子，code/user_ext1 新值是诱因，剥 callee_container 是性价比最高的止损动作。
created: 2026-04-25
updated: 2026-04-26
---

# 0 点活动上线导致 RPC 指标 series 暴涨

## 0x01 排查方法

### a. 适用场景

- APM 应用 RPC 指标在某个时间点（如活动上线、版本发布）出现 series 数突增。
- 原始 `rpc_*_handled_total` 自身基数已过高，无法直接用于分析。
- 业务侧通常已沉淀一份去 IP 的派生指标（如 `sum_without_ip_rpc_client_handled_total`），分析以派生指标为入口。
- 对端 trace 已过期，只能基于指标做归因。

### b. 排查步骤

#### 步骤 1：用 `count by (service_name, callee_service)` 在两个相邻窗口对比 ΔC

定位所有"边"维度上的新增/放大。

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

#### 步骤 2：反查每条新边的上游

对每个新增 `callee_service`，去掉 `service_name` 过滤，找出真正的主调，确定级联根：

```promql
count by (service_name, callee_service) (
  sum_over_time( <metric>{ callee_service="<新边的 callee>" }[30m] )
)
```

新边可能挂在已有根（如统一入口服务）下，识别后才能正确解读"为什么这些活动同时被点亮"。

#### 步骤 3：先把每条新增/放大的边按形态分类

| 形态 | 判定 | 含义 |
| --- | --- | --- |
| **全新边** | `C_before = 0, C_after > 0` | 前 30 min 完全未上报，0 点出现的 series 全是「新值」，直接看哪个维度 fan-out 最大 |
| **已有边放大** | `C_before > 0, C_after >> C_before` | 前 30 min 已稳态运行，0 点 ΔC 突变，需要分辨「新值驱动」和「fan-out 乘子」 |

两类形态的归因路径完全不同，混在一起讲会得出错误结论。

#### 步骤 4：识别隐藏维度

用 `topk` 拉若干条原始 series，对比它们的全部 label key/value：

```promql
topk(5, sum_over_time( <metric>{ <边> }[1h] ))
```

观察 5 条 series 中"其他 label 全相同、仅某一 label 在变"的那一列即为隐藏维度。

> 本次发现：业务自定义 `sum_without_ip_*` 仅剥离了 `caller_ip` / `callee_ip`，**未剥离 `callee_container`（被调 pod 名）**。

该标签仅在 callee 是 IEG-AMS 域 tRPC-Go 服务时出现，单边可贡献 800 倍展开。

#### 步骤 5：分辨"新值驱动"和"fan-out 乘子"

仅对"已有边放大"做。对每个候选维度独立跑 `count by`，跨 0 点：

```promql
count by (<dim>) (sum_over_time( <metric>{ <边> }[1m] ))
```

| 现象 | 维度角色 | 处理 |
| --- | --- | --- |
| 维度值集合**扩大**（0 点后出现新值） | **新值驱动**——业务诱因 | 重点关注是哪个新值（如新 `code`、新 `user_ext1`） |
| 维度值集合**不变**，但每个值的覆盖率/频次提升 | **fan-out 乘子**——基数放大器 | 关注剥它能消减多少 series |
| 维度只有少数固定值且不变 | 无关 | 忽略 |

确认新值之间的乘法关系：

```promql
count by (<新值维度 1>, <新值维度 2>) (
  sum_over_time( <metric>{ <边> }[1m] )
)
```

> **常见误区**：高基数维度（如 `callee_container` ~800 pod 名）很容易被误标为「主凶」
>
> 但如果 30m 窗口内值集合不变，它只是**乘子**——剥掉收益巨大，但不能解释「为什么 0 点突变」，真正的诱因永远在新值驱动里

#### 步骤 6：把 ΔC 折算回原始指标 series

`新增 series ≈ ΔC × R`，R 取上报该指标的服务副本数：

- 主调端（发出 `rpc_client_handled_total`）：`R = 主调副本数`。
- 被调端（发出 `rpc_server_handled_total`）：`R = 被调副本数`，仅当 callee 在本 APM 暴露 server metric 时才计入，外部 callee 不入账。

#### 步骤 7：跨 metric 家族放大

每条 `(edge × label combo)` 在 4 类 RPC metric 上同时上报，实际 series 数 = 单 metric × 乘子：

```text
乘子 = 1 × _total + 1 × _seconds_count + 1 × _seconds_sum + N × _seconds_bucket
N = 直方图 le 标签的取值数（含 +Inf）
```

实际跑业务时去 callee 应用拉一条原始 histogram 的 `le` 标签集合数即可，本案例 N=10，乘子 = 13。

### c. 结果输出建议

- 用一棵以级联根为顶点的拓扑树展示所有受影响边，按形态标注：
  - `[NEW SERVICE]` / `[NEW EDGE]`：边在 0 点前完全未点亮。
  - `★ multiplier: <维度>`：已有边被某个高基数维度 fan-out 撑大。
  - `driver: <新值维度>`：真正出现新值的维度（业务诱因）。
- 总账分主调端 / 被调端 / 单 metric / 跨 4 类 metric 四列。
- 优化建议按 `service_name + 剥离维度` 描述，按节省量降序，给出单次 PR 可砍多少。

## 0x02 结论（本案）

> - 业务：APM 应用 `hpjy-microservices-activities-production`（biz_id `-4228598`）
> - 时间：`2026-02-16 00:00 +0800`
> - 分析指标：`sum_without_ip_rpc_client_handled_total`
> - 副本数：
>   - `msgcenter`=480，`msgcenter-camp`=40
>   - `activities-{10139,10206,10212,10221}`=240
>   - `activities-60017`=120，其他 `activities-*`=120
> - histogram bucket：`le` 标签 10 个值（含 `+Inf`），跨 4 类 RPC metric 乘子 = 13

### a. 关键结论

- 0 点新增 series ≈ **616 K**（单 `rpc_client_handled_total`），跨 4 类 RPC metric ≈ **8.0 M**
- 用户原始关注的 `activities-10139` / `activities-10206` 链路只占 60 K（10 %）
- 真正的大头来自 `activities-60017` / `activities-10221` 调向 AMS 域服务的几条边（`amspkg`/`campamspkg`/`amshostpkg`，合计 ≈ 467 K，76 %）
- series 暴涨形态分两类，归因不同但止损动作一致：
  - **全新边**：`10221` → `amshostpkg`、`60017` → `campamspkg`、`60017` → `hpyd.php.inner.formal`
    - 边在 0 点前完全未点亮
    - 新值由 `callee_container`（~800 pod）/ `callee_method` 等高基数维度直接撑出
  - **已有边被放大**：`60017` → `amspkg`，series 从 540 跳到 2601
    - 30 min 窗口内 `callee_container` 值集合**几乎不变**，它只是 800 倍 fan-out **乘子**
    - 真正的「新值」是活动期出现的 `code=err_101` 与 `user_ext1=act_60017_check_in_req`
- 不论形态，最高性价比的止损都是给业务自定义 `sum_without_ip_*` 追加 `callee_container` 剥离：
  - 全新边：直接消除 ~800 个 series
  - 已有边放大：切断 fan-out 乘子，让上层 `code` / `user_ext1` 怎么涌也压不出来
- 仅给 `activities-60017` 与 `activities-10221` 加 `callee_container` 剥离即可消减 **≈ 467 K（占总量 76 %）**，单 PR 即可让 VM 入库延迟恢复

### b. 级联拓扑

0 点 16 个 activities 子服务经统一根 `msgcenter` / `msgcenter-camp` 同时被点亮，触发自身基数膨胀与下游二跳膨胀。

`ΔC = C[00:00, 00:30] − C[23:30, 00:00]`。

格式：

- `[service_name=…]` 是主调（emit metric 的服务 + 副本数）。
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
│   ├── --> callee_service=trpc.hpjy.activity-microservices.amshostpkg           ΔC=899  [NEW EDGE] driver: callee_container ~800 pods
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
    ├── --> callee_service=trpc.hpjy.activity-microservices.amspkg               ΔC=1293 已有边放大 540→2601；driver: code=err_101 + user_ext1=check_in_req；multiplier: callee_container ~800 pods
    ├── --> callee_service=trpc.hpjy.activity-microservices.campamspkg           ΔC=800  [NEW EDGE] driver: callee_container ~800 pods
    ├── --> callee_service=hpyd.php.inner.formal                                 ΔC=233  [NEW EDGE] driver: callee_method × user_ext1=act_60017_*
    ├── --> callee_service=trpc.hpjy.activity-microservices.redis-data           ΔC=16
    └── --> callee_service=trpc.hpjy.activitymicroservices.msgcenter.forward     ΔC=1
```

- `[NEW SERVICE]` / `[NEW EDGE]`：当晚首次上线的服务或当晚首次出现的调用边，所有 series 都是新值。
- `driver`：该边上真正出现新值的维度，是业务诱因。
- `multiplier`：该边上值集合不变、但提供 fan-out 倍数的高基数维度（剥离后 ΔC 大幅消减）。

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

| `callee_service` | 23:50 ~ 23:59 | 00:00 | 00:01 峰值 | 00:02 ~ 00:09 稳态 | 形态 |
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

| `service_name` | 23:50 ~ 23:59 | 00:00 | 00:01 峰值 | 00:04 峰值 | 00:02 ~ 00:09 稳态 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `activities-10139` | 7 | 11 | 44 | 63 | 44 |
| `activities-10206` | 9 | 9 | 40 | 64 | 40 |
| `activities-10212` | 60 | 60 | 60 | 87 | 59 ~ 60 |
| `activities-10221` | 108 | 111 | 124 | 135 | 108 ~ 117 |

主驱动维度为 `user_ext1=act_<id>_<action>_req`，每个活动开放后会有一组新的 `<action>` 涌入，叠加在原有 redis 调用上。

#### c.3 全新边：`callee_container` 直接撑出 800 倍 fan-out

`10221 → amshostpkg` 与 `60017 → campamspkg` 是当晚首次出现的边，0 点前 series 数为 0，0 点后一次性涌入 ~800 个 `callee_container` 值，构成新值本身

```promql
count by (service_name, callee_service, callee_container) (
  sum_over_time(sum_without_ip_rpc_client_handled_total{
    service_name=~"activity-microservices.activities-10221|activity-microservices.activities-60017",
    callee_service=~"trpc.hpjy.activity-microservices.amshostpkg|trpc.hpjy.activity-microservices.campamspkg"
  }[1m])
)
```

| `service_name` → `callee_service` | 23:59 distinct container | 00:01 distinct container | 形态 |
| --- | ---: | ---: | --- |
| `10221` → `amshostpkg` | 0 | ~800 | [NEW EDGE]，container 是真驱动 |
| `60017` → `campamspkg` | 0 | ~600 | [NEW EDGE]，container 是真驱动 |

这两条边里 `callee_container` 既是新值也是 fan-out 来源，剥它能消减全部增量。

#### c.4 已有边放大：辨析驱动 vs 乘子（`60017 → amspkg`）

这条边 23:50 已有 ~440 series 稳态，0:01 跳到 2601，乍看像 `callee_container` ~800 pod 主导，但拉开看会发现 container 的值集合在 0 点前后基本不变——它是乘子，不是驱动

##### 步骤 1：先看 `callee_container` 值集合是否扩大

```promql
count by (service_name, callee_service, callee_container) (
  sum_over_time(sum_without_ip_rpc_client_handled_total{
    service_name="activity-microservices.activities-60017",
    callee_service="trpc.hpjy.activity-microservices.amspkg"
  }[1m])
)
```

| 指标 | 23:50 ~ 23:59 | 00:00 ~ 00:09 |
| --- | ---: | ---: |
| 累积去重 container 数 | 799 | 800 |
| 两窗口交集 | — | 799 |

> 30 min 窗口内 container 集合几乎不变（只多 1 个）——**容器不是新值，是乘子**

##### 步骤 2：找真正出现新值的维度

依次跑 `count by (<dim>)` 跨 0 点，对比每个候选维度的值集合：

| 维度 | 23:59 已有值 | 00:01 新增值 | 角色 |
| --- | --- | --- | --- |
| `code` | `0` | `err_101`（活动期错误码） | **新值驱动** |
| `user_ext1` | `act_60017_lottery_req` | `act_60017_check_in_req`（新增业务动作） | **新值驱动** |
| `callee_method` | 12 个固定方法 | 0 | 无关 |
| `caller_method` | 4 个固定方法 | 0 | 无关 |
| `user_ext2` / `user_ext3` | 单值 | 0 | 无关 |

##### 步骤 3：交叉切片量化每个新值的贡献

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
- 剩余 19 % 是已有组合 `(0, lottery_req)` 的 container 覆盖率从 410 涨到 799——同一个乘子在更多 container 上点亮

##### 结论

- 真正诱因：活动期上线 `check_in_req` 业务动作 + 引入 `err_101` 错误码
- 真正放大器：800 个 `callee_container` 把每个新值扇出 800 倍
- 止损动作：剥 `callee_container` 直接砍掉 800 倍 fan-out，无论上层维度新增什么都压不出来，再追加 `code != 0 时才上报 user_ext1` 的业务侧规约可压缩残量

### d. 总账

`新增 series ≈ ΔC × R`，R 取上报该指标的服务副本数：

- 主调端（发出 `rpc_client_handled_total`）：R = 主调服务副本
- 被调端（发出 `rpc_server_handled_total`）：R = 被调服务副本
  - 本 APM 仅 `msgcenter` / `msgcenter-camp` 暴露 server metric，其他被调端不计入

#### d.1 按 caller 端逐项

出边明细见 `b. 级联拓扑` 中各 caller 子树的 `--> callee_service=…  ΔC=…` 行。

| caller `service_name` | R | ΔC 合计 | 主调端 series |
| --- | ---: | ---: | ---: |
| `msgcenter` | 480 | 119 | 57.1 K |
| `msgcenter-camp` | 40 | 6 | 0.24 K |
| `activities-10139` | 240 | 71 | 17.0 K |
| `activities-10206` | 240 | 64 | 15.4 K |
| `activities-10212` | 240 | 38 | 9.1 K |
| `activities-10221` | 240 | 947 | 227.3 K |
| `activities-60017` | 120 | 2343 | 281.2 K |
| **主调端合计** | — | **3588** | **≈ 607 K** |

#### d.2 单 metric 与跨 4 类总账

| 范围 | 主调端 | 被调端 | 单 metric 合计 | 跨 4 类 RPC metric 合计 |
| --- | ---: | ---: | ---: | ---: |
| `10139` / `10206` 链路 | 52.1 K | 8.1 K | ≈ 60 K | ≈ 0.78 M |
| 其他 ramp（`10212` / `10221` / `60017` / `msgcenter` / `msgcenter-camp` 放大） | 555.3 K | 0.5 K | ≈ 556 K | ≈ 7.23 M |
| **合计** | **≈ 607 K** | **≈ 8.6 K** | **≈ 616 K** | **≈ 8.0 M** |

「跨 4 类」乘子：

- 计数类：`client._total` / `client._seconds_count` / `client._seconds_sum`，各贡献 1 倍
- 直方图：`client._seconds_bucket`，每个 `le` 值一条 series，本案 `le` 共 10 个值（含 `+Inf`）
- 合计乘子 = 1 + 1 + 1 + 10 = **13**，被调端同理已合并到此列

### e. 优化建议

#### e.1 动作清单

| service_name | 剥离维度 | 单 metric 节省 | 跨 4 类 metric 合计节省（×13） |
| --- | --- | ---: | ---: |
| `activity-microservices.activities-60017` | `callee_container` | ≈ 251 K | ≈ 3.27 M |
| `activity-microservices.activities-10221` | `callee_container` | ≈ 216 K | ≈ 2.81 M |
| `activity-microservices.activities-*`（全部活动服务） | `user_ext1` | ≈ 17 K | ≈ 0.22 M |

#### e.2 各动作收益来源

- **`activities-60017` 剥 `callee_container`**（R=120）：
  - `60017` → `campamspkg`（800 ΔC × 120 = 96 K，[NEW EDGE]）：800 个 container 是真新值，剥后整条边收敛
  - `60017` → `amspkg`（1293 ΔC × 120 = 155 K，已有边放大）：
    - container 是 800 倍 fan-out 乘子
    - 剥后即使 `code=err_101` 与 `user_ext1=check_in_req` 等新值继续涌入也只能各打出一条 series，整条边压回单位数
- **`activities-10221` 剥 `callee_container`**（R=240）：
  - `10221` → `amshostpkg`（899 ΔC × 240 = 216 K，[NEW EDGE]）：消减 ~800 个被调 pod 名展开
- **`activities-*` 剥 `user_ext1`**：
  - 把所有活动服务上报的 `user_ext1=act_<id>_<action>_req` 合并为单一空值
  - 覆盖各活动 → `redis-data` / `msgcenter.forward` / `hpyd.php.inner.formal` 等边内的乘法放大

> 注：`callee_container` 这一动作对「已有边放大」场景的价值远高于直觉——它不靠预测业务会上什么新动作或新错误码，而是直接砍掉乘子，对未来类似活动也免疫

#### e.3 推荐止损路径

单次 PR 在以下两个 `service_name` 的剥离规则中追加 `callee_container`：

```text
activity-microservices.activities-60017
activity-microservices.activities-10221
```

预计立刻消减 ≈ **467 K**（占 0 点单 metric 新增量 76 %）/ ≈ **6.08 M** 跨 4 类 metric。

VM 入库延迟可恢复。

`user_ext1` 优化（≈ 17 K / ≈ 0.22 M，占比 < 3 %）留作二期，可结合活动级业务监控诉求一并评估。
