---
title: bk-collector 指标元信息调研与性能报告
tags: [collector, metrics, metadata, benchmark, cache]
description: 对照协议源码和实际缓存实现，量化元信息去重的正确性、内存与发送成本
created: 2026-09-15
updated: 2026-09-15
---

# bk-collector 指标元信息调研与性能报告

**选型：短期用 Go map 保存待发原文，长期用低误判率 Bloom 记录成功发送的版本。** 默认目标误判率为 `1e-6`，每 `2 h` 强制补报一次当前观测快照。

性能分别测量去重缓存（sent）和待发缓冲（pending）：前者测到一千万主键，后者包含本轮发送快照占用的完整值内存。

Bloom 记住的是历史版本：元信息跨周期回退为旧值时，也可能等到强制补报才恢复。只出现一次、又被误判的项无法事后找回；内存缓存不提供可靠投递。

## 0x01 代码证据

源码基线：本地 collector，Git HEAD 为 `b7f6acae5445cb18be7e115e3860ba8372cf7033`。

| 证据 | 已核实的事实 |
| --- | --- |
| [<源码> collector/exporter/converter/metrics.go](https://github.com/ZhuoZhuoCrayon/bkmonitor-datalink/blob/b7f6acae5445cb18be7e115e3860ba8372cf7033/pkg/collector/exporter/converter/metrics.go) | `Extract` 先 `NormalizeName` 再 `SetName`，随后按类型拆分，Histogram 支持 optional sum／min／max |
| [<源码> collector/exporter/converter/tars.go](https://github.com/ZhuoZhuoCrayon/bkmonitor-datalink/blob/b7f6acae5445cb18be7e115e3860ba8372cf7033/pkg/collector/exporter/converter/tars.go) | Stat 分原始与聚合输出，IsDropOriginal 控制原始项，推导服务会改写 dimensions |
| [<源码> collector/receiver/remotewrite/http.go](https://github.com/ZhuoZhuoCrayon/bkmonitor-datalink/blob/b7f6acae5445cb18be7e115e3860ba8372cf7033/pkg/collector/receiver/remotewrite/http.go) | 通过 Validate 后解码，只把 `writeReq.Timeseries` 放入 Record |
| [<源码> collector/define/record.go](https://github.com/ZhuoZhuoCrayon/bkmonitor-datalink/blob/b7f6acae5445cb18be7e115e3860ba8372cf7033/pkg/collector/define/record.go) | 结构只有 Timeseries，无 Metadata 或来源描述 |
| [<源码> collector/processor/metricsfilter/factory.go](https://github.com/ZhuoZhuoCrayon/bkmonitor-datalink/blob/b7f6acae5445cb18be7e115e3860ba8372cf7033/pkg/collector/processor/metricsfilter/factory.go) | OTLP 有名称替换，Remote Write relabel 可以修改名称和范围所用标签 |
| [<源码> collector/go.mod](https://github.com/ZhuoZhuoCrayon/bkmonitor-datalink/blob/b7f6acae5445cb18be7e115e3860ba8372cf7033/pkg/collector/go.mod) | Go `1.23.0`，pdata `v0.61.0`，Prometheus 经 replace 使用 `v0.38.0`，go-cache 为 `v2.1.0` |
| [<源码> collector/exporter/converter/pushgateway.go](https://github.com/ZhuoZhuoCrayon/bkmonitor-datalink/blob/b7f6acae5445cb18be7e115e3860ba8372cf7033/pkg/collector/exporter/converter/pushgateway.go) | trpc 兼容分支删除 `_name`／`_type` 并改名，描述须先保留、身份须后绑定 |
| [<源码> collector/processor/tokenchecker/factory.go](https://github.com/ZhuoZhuoCrayon/bkmonitor-datalink/blob/b7f6acae5445cb18be7e115e3860ba8372cf7033/pkg/collector/processor/tokenchecker/factory.go) | 提供鉴权后的 DataID |

[Controller](https://github.com/ZhuoZhuoCrayon/bkmonitor-datalink/blob/b7f6acae5445cb18be7e115e3860ba8372cf7033/pkg/collector/controller/controller.go) 调用既有 [Exporter](https://github.com/ZhuoZhuoCrayon/bkmonitor-datalink/blob/b7f6acae5445cb18be7e115e3860ba8372cf7033/pkg/collector/exporter/exporter.go) 的生命周期入口：New 创建 converter，Start 启动消费者，Stop 执行 converter.Clean、cancel 和 wg.Wait。消费者目前在协程内部执行 wg.Add，接入方案需将等待范围移至 wait.Until 外层。

OTP 文件被仓库 ignore 规则排除，本地证据为 [receiver.go](/Users/sandrincai/Project/Github/bk/bkmonitor-datalink/pkg/collector/receiver/otpreceiver/receiver.go) 和 [otp_to_prom.go](/Users/sandrincai/Project/Github/bk/bkmonitor-datalink/pkg/collector/receiver/otpreceiver/internal/otp_to_prom.go)。

`receiver.go` 的 SHA-256 为 `d881a25dabbdcd6731d69f3138c56c6b51a23bfe554dcc1cba5866c9539ccf5d`，`otp_to_prom.go` 为 `cad6ce2a2221daed02ab78ab101c12d3a96699383dd4272a186a0bc5dd53cce8`。

OTP 的 Client／Server 和自定义指标字段见本地 [otp.pb.go](/Users/sandrincai/Project/Github/bk/bkmonitor-datalink/pkg/collector/receiver/otpreceiver/internal/model/otp.pb.go)，Aggregation 枚举及 RPC 语义说明见 [omp.pb.go](/Users/sandrincai/Project/Github/bk/bkmonitor-datalink/pkg/collector/receiver/otpreceiver/internal/model/omp.pb.go)。内置 RPC 的秒单位有字段说明，自定义 COUNTER／SUM 的标量没有单位声明。

## 0x02 协议判断

### a. Remote Write 能拿到什么

| 协议／实现 | 有效信息 | 对 collector 的结论 |
| --- | --- | --- |
| v1 标准最小消息 | 标准保留 field `3`，未把 metadata 定为通用保证 | metadata 为可选能力 |
| Prometheus `v2.38.0` 实现 | field `3` 为 Metadata，含指标族名称、类型、描述和单位 | 依赖可解码，范围须由使用方明确提供 |
| v1 MetadataWatcher | 定时单独发送元信息，没有 TimeSeries 标签 | 缺少实际序列绑定，本方案暂不登记独立元信息 |
| v2 消息 | TimeSeries 内有 Metadata，名称来自 labels 的符号引用 | 可改善绑定，但需要新的消息解码与协议兼容工作 |

- *[1] 来源：[v1 标准](https://prometheus.io/docs/specs/prw/remote_write_spec/)、[remote.proto](https://github.com/prometheus/prometheus/blob/v2.38.0/prompb/remote.proto)、[types.proto](https://github.com/prometheus/prometheus/blob/v2.38.0/prompb/types.proto)、[v2 规范](https://prometheus.io/docs/specs/prw/remote_write_spec_2_0/)。*

Prometheus `v2.38.0` 默认启用 metadata 发送，间隔 `1 min`，每批最多 `500` 项。[DefaultMetadataConfig](https://github.com/prometheus/prometheus/blob/v2.38.0/config/config.go#L180)

### b. Counter 指标族名称不等于序列名

相同的指标族元信息不足以确定 Counter 的最终名称。固定 Prometheus `v0.38.0` 解析器的实测反例如下：

| 输入格式 | TYPE 声明 | 实际序列名 | v1 Metadata |
| --- | --- | --- | --- |
| Prometheus 文本 | `requests counter` | `requests` | 指标族名称为 requests，type 为 COUNTER |
| OpenMetrics | `requests counter` | `requests_total` | 指标族名称为 requests，type 为 COUNTER |

- *[1] 两者的元信息单独编码后均为 `1a0c080112087265717565737473`。代码见 [protocol_test.go](./validation/protocolcheck/protocol_test.go)，输出由该测试写入 `validation/results/protocol.txt`。*

Prometheus 的 Type 解析结果保留指标族名称原文，`AppendMetadata` 直接复制指标族名称字段，不携带原 exposition 格式。OpenMetrics 为 Counter 样本追加 `_total`，因此仅从这份 v1 Metadata 无法唯一还原最终序列名。[OpenMetrics 命名规则](https://github.com/prometheus/OpenMetrics/blob/v1.0.0/specification/OpenMetrics.md#counter)、[AppendMetadata](https://github.com/prometheus/prometheus/blob/v2.38.0/storage/remote/queue_manager.go)

接入独立 v1 Metadata 前，需定义指标族与输出序列的对应规则。

### c. 协议语义与平台约定

- 累计方式：delta 为本周期增量，cumulative 为累计值，OTP 全部为 delta，Gauge 的 delta 表示本次值。
- 汇聚方式：usage 指定默认操作，选择 increase 还须确认累计值单调。
- Histogram：bucket 累加描述分桶关系，累计方式取来源协议。
- 分位数：各实例分位数的平均值不能代表总体分位数。
- 采集周期：interval 取来源明确提供的周期，未知时为 null。
- 解码能力：以 receiver 的实际协议及依赖版本为准。

来源：[OTel 数据模型](https://opentelemetry.io/docs/specs/otel/metrics/data-model/)、[OTel 与 Prometheus 的兼容规则](https://opentelemetry.io/docs/specs/otel/compatibility/prometheus_and_openmetrics/)、[Prometheus exposition 格式](https://prometheus.io/docs/instrumenting/exposition_formats/)。

## 0x03 业界机制与取舍

候选方案按去重精度、内存布局和淘汰方式比较，性能数据见 [独立实验](#0x05-内存与性能结果)。

### a. 与本需求最接近的实现

Prometheus 的 MetadataWatcher 每轮构造 `map[MetricMetadata]struct{}`，按 name／type／help／unit 去重，再批量发送全部活跃定义。[MetadataWatcher](https://github.com/prometheus/prometheus/blob/v2.38.0/storage/remote/metadata_watcher.go#L120)

Prometheus scrape cache 按名称索引元信息，连续超过 `10` 轮未出现时清理，保留时间取决于采集记录。[scrapeCache](https://github.com/prometheus/prometheus/blob/v2.38.0/scrape/scrape.go#L854)

本方案在成功发送后登记 Bloom 指纹，指纹覆盖完整主键和值，包括单位、描述和 usage。

### b. 候选机制比较

| 候选 | 保证与代价 | 本场景取舍 |
| --- | --- | --- |
| Prometheus 周期完整值集合 | 每轮合并并发送活跃定义 | 实现简单，重复发送量高 |
| 完整结构体 map + TTL | 精确保存每个 key 的最新成功值 | 精确去重对照，内存成本较高 |
| go-cache `v2.1.0` | string key、interface value、通用锁与 TTL 扫描 | 原文内存与扫描成本较高 |
| 完整主键 + SHA-256 值摘要 | 缩减 sent 的 value，仍有摘要碰撞概率和编码成本 | 适合长描述，仍需逐键存储 |
| **单代 Bloom + 周期强制补报** | 位图省内存，存在误判和历史版本命中 | **采用：以可接受的少量遗漏换取长期内存下降** |
| Ristretto | TinyLFU 按访问频率决定是否缓存，按容量淘汰，可能丢弃新 Set | 适合作为 sent 的有损缓存 |
| BigCache | 字节数组减少 GC 扫描，以哈希值索引，碰撞时可能覆盖原值 | 降低 GC 扫描成本，仍需保存原文 |
| Cuckoo filter | 判断某项是否存在，允许少量误判，支持单项删除和扩容 | 额外删除能力对整代清理收益有限 |

- *[1] 实现来源：[go-cache](https://github.com/patrickmn/go-cache/tree/v2.1.0)、[Bloom](https://github.com/bits-and-blooms/bloom)、[Ristretto](https://github.com/dgraph-io/ristretto)、[BigCache](https://github.com/allegro/bigcache)、[Cuckoo](https://redis.io/docs/latest/develop/data-types/probabilistic/cuckoo-filter/)。*
- *[2] 回退识别：精确处理 A → B → A 需要保存每个 key 的最新成功版本。*

go-cache 的 `Get` 不刷新 TTL，`DeleteExpired` 在锁内扫描整个 map；完整值 map 对照同样从发送成功开始计时。[go-cache 源码](https://github.com/patrickmn/go-cache/blob/v2.1.0/cache.go)

Ristretto 丢弃新 Set 会导致下次重复发送，适用于 sent；pending 需要保留待发原文直到确认或显式丢弃。[Ristretto 的 Set 语义](https://github.com/dgraph-io/ristretto#how-are-you-achieving-this-performance-what-shortcuts-are-you-taking)

### c. Bloom 误判与强制补报

目标误判率决定 Bloom 的位图大小。每组先写满设计容量，再各探测一百万个未见指纹和一百万个描述变化后的指纹。

| 成功版本容量 | 目标误判率 | 位图 MiB | 未见版本误判 | 描述变化误判 |
| --- | ---: | ---: | ---: | ---: |
| 100,000 | 1e-2 | 0.114 | 10,284 | 10,114 |
| 100,000 | 1e-4 | 0.229 | 83 | 100 |
| 100,000 | **1e-6** | **0.343** | **1** | **1** |
| 1,000,000 | 1e-2 | 1.143 | 9,944 | 9,954 |
| 1,000,000 | 1e-4 | 2.285 | 91 | 101 |
| 1,000,000 | **1e-6** | **3.428** | **1** | **0** |

- *[1] `make bloom` 写入 `validation/results/bloom_targets.txt` 与 `bloom_sizing.txt`。零次命中不表示概率为零。*

因此选 `1e-6`：百万版本位图仍只有约 `3.43 MiB`，比 `1e-4` 多约 `1.14 MiB`，却将目标误判率降低两个数量级。该参数使用 `20` 次哈希探测。[Bloom 参数公式](https://github.com/bits-and-blooms/bloom)

位图按本代不同 `(Key, Value)` 版本估算容量，实现以成功 Add 次数保守计数。若不控制插入量，写入两倍设计容量时理论误判率会升至约 `0.327%`，所以达到容量必须重置；容量清理保持原补报时间。

随机误判率可以通过增加位图降低，历史版本命中则必须由补报处理：

| 同一个 key 的观测顺序 | 下游期望值 | Bloom 命中后可能留下的值 |
| --- | --- | --- |
| A 首次发送成功 | A | A |
| 变为 B，发送成功 | B | B |
| 再次变为 A | A | B，历史 A 仍在 Bloom 中 |

每 `2 h` 的补报快照绕过 Bloom，恢复当前值。未发送的强制项跨周期保留标记，避免被 `5 s` Flush 期限打断后重新去重；持续新增、失败和容量丢弃会延长恢复时间。

## 0x04 实验方法

[isolated_performance_test.go](./validation/isolated_performance_test.go)用不同指标名生成样本：DataID 为 `1`、ScopeType 为 DEFAULT、Scope 为空、Metric 为 `metric_%08d`。N 直接表示生成的主键数量。

| 对象 | 内存测量 | 存在判断 |
| --- | --- | --- |
| sent | 每个主键写入一个版本，填满 Bloom，GC 后只保留过滤器状态 | 分别测位图判断和含指纹计算的存在判断 |
| 发送缓冲 | 动态增长的 map 保存 N 条完整值，另测两个 map 同时存活 | 不测 sent 或网络 |

- *[1] 运行环境：Go `1.23.0`、darwin/arm64、Apple M4 Pro、14 个逻辑 CPU、48 GiB 内存。*
- *[2] 内存测量：独立进程 GC 后的堆内存（HeapAlloc）增量，非空字符串独立分配，输入集合不保留。*
- *[3] 查询样本：在完整插入范围内均匀取最多 `65,536` 个已存在键，循环查询，每组运行 `200 ms × 3`。*
- *[4] 过滤器：原型 Bloom 使用完整版本指纹与双重哈希，目标误判率 `10⁻⁶`，每次查询探测 `20` 位。*

## 0x05 内存与性能结果

### a. sent

| 主键数 | 去重缓存内存（MiB） | 位图判断 ns/op *[2]* | 含指纹计算 ns/op *[3]* |
| ---: | ---: | ---: | ---: |
| 10,000 | 0.04 | 18.41 | 229.5 |
| 100,000 | 0.35 | 19.15 | 226.7 |
| 1,000,000 | 3.45 | 22.55 | 209.2 |
| 10,000,000 | 34.30 | 102.60 | 374.7 |

- *[1] 原始结果由 `make sent` 写入 `validation/results/sent_memory.txt` 与 `sent_lookup.txt`。*
- *[2] 位图判断：用预计算指纹检查 Bloom 的 `20` 个位位置，每次分配 `0 B`。*
- *[3] 含指纹计算：从 Key + Value 计算哈希指纹（含过滤器版本号），再执行位图判断，每次分配 `320 B`。*
- *[4] 测量范围：两列均为同一个 Bloom 的单次查询耗时，取三次中位数，不含 Store 锁与网络。*
- *[5] 内存范围：垃圾回收（GC）后保留的位图及分配器开销，千万项位图为 `35,943,976 B`，pending 与快照另计。*
- *[6] 容量规划：按成功版本数计，需为同一 key 在周期内的变化预留容量。*

### b. Exporter 发送缓冲

| 每个缓冲的主键数 | 单条描述大小（B） | 待发缓冲（MiB） | 缓冲 + 发送快照（MiB） |
| ---: | ---: | ---: | ---: |
| 10,000 | 64 | 4.19 | 8.37 |
| 10,000 | 1,024 | 13.34 | 26.68 |
| 100,000 | 64 | 38.29 | 76.49 |
| 100,000 | 1,024 | 129.82 | 259.67 |
| 1,000,000 | 64 | 500.37 | 1,000.69 |
| 1,000,000 | 1,024 | 1,415.89 | 2,831.74 |

- *[1] 原始结果由 `make buffer` 写入 `validation/results/buffer_memory.txt`。*
- *[2] 单条描述大小：`__description` 按 UTF-8 编码后的字节数，主键和其他字段也计入内存列。*
- *[3] 双缓冲：pending 与快照各保存 N 条独立记录，不含 sent、JSON 编码体、网络缓冲或 GC 峰值。*
- *[4] 容量配置：pending 与 sent 独立设置，超过十万 pending 的实验需提高默认上限。*

## 0x06 补报周期与发送量

### a. 周期选择

模拟 `48 h`：每分钟观察 `1,000` 个稳定键，并新增 `100` 个一次性键，发送全部成功，Bloom 容量为十万版本、目标误判率为 `10⁻⁶`。

| 强制补报周期 | 实际发送项数 | 单轮最大发送项数 | 两次清理间的最多登记次数 | 重置次数 |
| --- | ---: | ---: | ---: | ---: |
| 15 min | 480,000 | 1,100 | 2,500 | 192 |
| 2 h | 312,000 | 1,100 | 13,000 | 24 |
| 24 h | 292,000 | 1,100 | 100,000 | 4 |

- *[1] `make bloom-store` 写入 `validation/results/bloom_store_ttl.txt`。重置包含启动首轮。`24 h` 触发容量重置，因此比精确 TTL 对照多发送 `2,000` 项；固定补报时钟保持不变。*

默认 `2 h` 在本负载下仅需保留 `13,000` 个成功版本，十万容量有余量。容量规划应覆盖一个周期内的活跃定义、新增和变化版本；百万活跃主键需要相应提高版本容量，否则提前重置会增加重复发送。

### b. 冷启动与发送边界

每批同时限制 `1,000` 项和 `256 KiB`，开始间隔为 `100 ms`，每轮 Flush 最多运行 `5 s`。超时后的强制项保留到下一分钟，不重新受 Bloom 去重。

| 待发主键数 | 单条描述 64 B：轮数／耗时 | 单条描述 1,024 B：轮数／耗时 |
| ---: | ---: | ---: |
| 10,000 | 1 / 1.0 s | 1 / 4.7 s |
| 100,000 | 3 / 120.6 s | 10 / 542.3 s |
| 1,000,000 | 22 / 1,261.4 s | 95 / 5,643.9 s |

- *[1] 实验条件：唯一指标样本、真实 JSON 与模拟时钟（`make buffer` 写入 `validation/results/buffer_coldstart.txt`），无新增、无失败，编码与网络耗时按零计算。*
- *[2] 耗时：首次 Flush 到最后一批开始发送的间隔，结果为理想最短耗时，启动等待与重新采集时间另计。*
- *[3] 结果校验：每轮最多 `50` 批，每批至多 `262,144 B`，确认数等于初始键数，实验容量设置为样本总量。*

内存预算包含 sent、pending、本轮发送快照、编码批次与垃圾回收期间的额外内存。清空 Bloom 后依靠 pending 与后续 Observe 补报。

## 0x07 验证结果

Bloom 原型通过行为测试、`go test -race ./...` 和 `go vet ./...`，覆盖成功确认、历史回退、误判补报、Force 保留、并发新值、容量重置与发送限制。

- `make bloom-store` 写入 `validation/results/bloom_store_behavior.txt`：缓存状态机用例。
- `make test` 写入 `validation/results/split_tests.txt`：独立实验工程回归结果。
- [实现验收](./PLAN.md#b-实现验收)：待实施的 Store／Exporter 拆分、Clean、生命周期与 collector 接入。
