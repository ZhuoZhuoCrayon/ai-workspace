---
title: 0 点活动上线导致 RPC 指标 series 暴涨
tags: [apm, rpc, cardinality, series-spike, callee-container, sum-without-ip]
description: 通过 ΔC 边对比 + 维度拆解 + 隐藏维度识别，定位活动上线引发的 series 暴涨主凶为业务自定义 sum_without_ip_* 漏剥 callee_container
created: 2026-04-25
updated: 2026-04-25
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

#### 步骤 3：对 ΔC 最大的边做维度拆解，验证主驱动

```promql
count by (callee_method, caller_method, caller_service,
          code, code_type, user_ext1, user_ext2, user_ext3) (
  sum_over_time( <metric>{ <边> }[1h] )
)
```

每行 count 值 = 该 (group by 字段组合) 下的 series 数。

- 若每行 count = 1：`group by` 字段已覆盖全部变化维度，C 等于行数。
- 若 `sum-of-counts ≠ 行数`：**还有未列入 group by 的隐藏维度**，进入步骤 4。

#### 步骤 4：识别隐藏维度

用 `topk` 拉若干条原始 series，对比它们的全部 label key/value：

```promql
topk(5, sum_over_time( <metric>{ <边> }[1h] ))
```

观察 5 条 series 中"其他 label 全相同、仅某一 label 在变"的那一列即为隐藏维度。

> 本次发现：业务自定义 `sum_without_ip_*` 仅剥离了 `caller_ip` / `callee_ip`，**未剥离 `callee_container`（被调 pod 名）**。

该标签仅在 callee 是 IEG-AMS 域 tRPC-Go 服务时出现，单边可贡献 800 倍展开。

#### 步骤 5：把 ΔC 折算回原始指标 series

`新增 series ≈ ΔC × R`，R 取上报该指标的服务副本数：

- 主调端（发出 `rpc_client_handled_total`）：`R = 主调副本数`。
- 被调端（发出 `rpc_server_handled_total`）：`R = 被调副本数`，仅当 callee 在本 APM 暴露 server metric 时才计入，外部 callee 不入账。

#### 步骤 6：跨 metric 家族放大

每条 `(edge × label combo)` 实际产生 17 条 series：

```text
1 × _total + 1 × _seconds_count + 1 × _seconds_sum + N × _seconds_bucket
（默认 N=14：11 个分桶 + +Inf + 客户端首发 0 桶 + ...）
```

总量估算：`单 metric 新增 × 17`。

### c. 结果输出建议

- 用一棵以级联根为顶点的拓扑树展示所有受影响边，标 `[NEW SERVICE]` / `★（隐藏维度主导）` / `driver: <主驱动维度>`。
- 总账分主调端 / 被调端 / 单 metric / 跨 4 类 metric 四列。
- 优化建议按 `service_name + 剥离维度` 描述，按节省量降序，给出单次 PR 可砍多少。

## 0x02 结论（本案）

> 业务：APM 应用 `hpjy-microservices-activities-production`（biz_id `-4228598`），
> 时间 `2026-02-16 00:00 +0800`，
> 分析指标 `sum_without_ip_rpc_client_handled_total`，
> 副本数 `msgcenter` / `msgcenter-camp` = 240，`activities-*` = 120。

### a. 关键结论

- 0 点新增 series ≈ **454 K**（单 `rpc_client_handled_total`），跨 4 类 RPC metric ≈ **7.7 M**。
- 主凶不是用户原始关注的 `activities-10139` / `activities-10206` 链路（仅 35 K，8 %），
  而是业务自定义的 `sum_without_ip_*` **漏剥了 `callee_container`（被调 pod 名）**。
- 仅 `activities-60017` 与 `activities-10221` 两个 `service_name` 上报的 `callee_container` 泄漏，就贡献了 **≈ 359 K，占总量 79 %**。
- 立即止损：单 PR 给这 2 个 `service_name` 追加 `callee_container` 剥离规则，VM 入库延迟可恢复。

### b. 级联拓扑

0 点 16 个 activities 子服务经统一根 `msgcenter` / `msgcenter-camp` 同时被点亮，触发自身基数膨胀与下游二跳膨胀。

`ΔC = C[00:00, 00:30] − C[23:30, 00:00]`。

格式：

- `[service_name=…]` 是主调（emit metric 的服务 + 副本数）。
- `--> callee_service=…` 是它的一条出边。

```text
[service_name=activity-microservices.msgcenter]   (R=240)
├── --> callee_service=trpc.hpjy.activity-microservices.activities.10139         ΔC=25  [NEW SERVICE]
│
│   [service_name=activity-microservices.activities-10139]   (R=120)
│   ├── --> callee_service=trpc.hpjy.activity-microservices.redis-data           ΔC=56   driver: user_ext1=act_10139_{assist|roll|send}_req
│   ├── --> callee_service=trpc.hpjy.activity-microservices.msgcenter            ΔC=8
│   └── --> callee_service=trpc.hpjy.activitymicroservices.msgcenter.forward     ΔC=7
│
├── --> callee_service=trpc.hpjy.activity-microservices.activities.10206         ΔC=16  [NEW SERVICE]
│
│   [service_name=activity-microservices.activities-10206]   (R=120)
│   ├── --> callee_service=trpc.hpjy.activity-microservices.redis-data           ΔC=54   driver: user_ext1=act_10206_{click|feed}_req
│   ├── --> callee_service=trpc.hpjy.activity-microservices.msgcenter            ΔC=9
│   └── --> callee_service=trpc.hpjy.activitymicroservices.msgcenter.forward     ΔC=1
│
├── --> callee_service=trpc.hpjy.activity-microservices.activities.10212         ΔC=4
│   [service_name=activity-microservices.activities-10212]   (R=120)
│   └── --> callee_service=trpc.hpjy.activity-microservices.redis-data           ΔC=38   driver: user_ext1=act_10212_*_req
│
├── --> callee_service=trpc.hpjy.activity-microservices.activities.10221         ΔC=5
│   [service_name=activity-microservices.activities-10221]   (R=120)
│   ├── --> callee_service=trpc.hpjy.activity-microservices.amshostpkg           ΔC=899  ★ driver: callee_container ~800 pods
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

[service_name=activity-microservices.msgcenter-camp]   (R=240?)
├── --> callee_service=trpc.hpjy.activity-microservices.activities.60009         ΔC=1
├── --> callee_service=trpc.hpjy.activity-microservices.activities.60014         ΔC=1
└── --> callee_service=trpc.hpjy.activity-microservices.activities.60017         ΔC=4
    [service_name=activity-microservices.activities-60017]   (R=120)
    ├── --> callee_service=trpc.hpjy.activity-microservices.amspkg               ΔC=1293 ★ driver: callee_container ~800 pods
    ├── --> callee_service=trpc.hpjy.activity-microservices.campamspkg           ΔC=800  ★ driver: callee_container ~800 pods
    ├── --> callee_service=hpyd.php.inner.formal                                 ΔC=233   driver: callee_method × user_ext1=act_60017_*
    ├── --> callee_service=trpc.hpjy.activity-microservices.redis-data           ΔC=16
    └── --> callee_service=trpc.hpjy.activitymicroservices.msgcenter.forward     ΔC=1
```

- `[NEW SERVICE]`：当晚首次上线的服务。
- `★`：`callee_container` 主导的边，剥离后 ΔC 接近 0。
- `driver`：该边主要被哪个保留维度放大。

### c. 总账

`新增 series ≈ ΔC × R`，R 取上报该指标的服务副本数：

- 主调端（发出 `rpc_client_handled_total`）：R = 主调服务副本。
- 被调端（发出 `rpc_server_handled_total`）：R = 被调服务副本，本 APM 仅 `msgcenter` / `msgcenter-camp` 暴露 server metric，其他被调端不计入。

| 范围 | 主调端 | 被调端 | 单 metric 合计 | 跨 4 类 RPC metric 合计 |
| --- | ---: | ---: | ---: | ---: |
| `10139` / `10206` 链路 | 26 K | 9 K | ≈ 35 K | ≈ 595 K |
| 其他活动 ramp（`10212` / `10221` / `60017` / `msgcenter` 放大） | 414 K | 5 K | ≈ 419 K | ≈ 7.12 M |
| **合计** | **440 K** | **14 K** | **≈ 454 K** | **≈ 7.7 M** |

`跨 4 类 = client._total + client._seconds_count + client._seconds_sum + client._seconds_bucket`
（按 14 个分桶估算）= 17 倍，被调端同理已合并到此列。

### d. 优化建议

#### d.1 动作清单

| service_name | 剥离维度 | 单 metric 节省 | 跨 4 类 metric 合计节省 |
| --- | --- | ---: | ---: |
| `activity-microservices.activities-60017` | `callee_container` | ≈ 251 K | ≈ 4.27 M |
| `activity-microservices.activities-10221` | `callee_container` | ≈ 108 K | ≈ 1.83 M |
| `activity-microservices.activities-*`（全部活动服务） | `user_ext1` | ≈ 17 K | ≈ 290 K |

#### d.2 各动作收益来源

- **`activities-60017` 剥 `callee_container`**：消减 `60017` → `amspkg`（154 K）与
  `60017` → `campamspkg`（96 K）两条边里 ~800 个被调 pod 名带来的展开。
- **`activities-10221` 剥 `callee_container`**：消减 `10221` → `amshostpkg`（108 K）一条边里 ~800 个被调 pod 名展开。
- **`activities-*` 剥 `user_ext1`**：把所有活动服务上报的 `user_ext1=act_<id>_<action>_req`
  合并为单一空值，覆盖各活动 → `redis-data` / `msgcenter.forward` / `hpyd.php.inner.formal`
  等边内的乘法放大。

#### d.3 推荐止损路径

单次 PR 在以下两个 `service_name` 的剥离规则中追加 `callee_container`：

```text
activity-microservices.activities-60017
activity-microservices.activities-10221
```

预计立刻消减 ≈ **359 K**（占 0 点单 metric 新增量 79 %）/ ≈ **6.1 M** 跨 4 类 metric。

VM 入库延迟可恢复。

`user_ext1` 优化（≈ 17 K / ≈ 290 K，占比 < 5 %）留作二期，可结合活动级业务监控诉求一并评估。
