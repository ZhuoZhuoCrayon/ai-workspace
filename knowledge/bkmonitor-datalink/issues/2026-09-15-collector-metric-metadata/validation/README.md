# 指标元信息验证工程

本工程验证缓存算法与性能，按去重缓存（sent）和待发缓冲（pending）分别测量，样本使用不同的指标名。

## 0x01 运行

Go 版本按 [go.mod](./go.mod) 使用 `1.23.0`，在本目录执行：

```bash
make sent
make buffer
make test
```

- *[1] 本机使用 `source "$HOME/.gvm/scripts/gvm" && gvm use go1.23.0` 切换工具链。*
- *[2] sent 与 buffer 顺序执行，避免大内存实验干扰单次查询计时。*
- *[3] make test 执行 `go test -race ./...` 与 `go vet ./...`，大规模实验由前两个命令单独运行。*

## 0x02 性能结果

`results/` 由本机 `make` 生成，不入库。结论见 [REPORT](../REPORT.md#0x05-内存与性能结果)。

| 部分 | 范围 | 本地输出 |
| --- | --- | --- |
| sent 内存 | 一万至一千万主键，每个主键只写入一个版本，目标误判率 `10⁻⁶` | `results/sent_memory.txt` |
| sent 存在判断 | 预计算指纹与完整版本指纹两条路径，各三次 | `results/sent_lookup.txt` |
| 发送缓冲 | 一万／十万／百万项，单条 `__description` 为 `64 B`／`1,024 B`，pending 与双缓冲分别量测 | `results/buffer_memory.txt` |
| 缓冲排空 | 真实 JSON 与模拟时钟，批次字节、数量、开始间隔及整轮期限 | `results/buffer_coldstart.txt` |

- *[1] [isolated_performance_test.go](./isolated_performance_test.go)生成唯一指标名，sent 只保留 Bloom，缓冲只保留完整值 map，均用独立进程量测 GC 后保留的内存。*
- *[2] [performance.sh](./performance.sh)写入 `results/`，[REPORT](../REPORT.md#0x05-内存与性能结果)说明采样、计时和内存范围。*
- *[3] 其他实验：make experiment／bloom／bloom-store 分别运行缓存对照、Bloom 参数及行为实验。*

## 0x03 算法与协议验证

[BloomStore](./bloom_store.go)包含周期缓冲、成功版本过滤、发送数量与速率限制和 Force 补报，[Store](./store.go)保留精确完整值对照。

| 验证 | 证据 |
| --- | --- |
| 值回退、误判补报、失败回填、并发新值和容量重置 | [bloom_store_test.go](./bloom_store_test.go) |
| 批次、期限与冷启动 | [bloom_store_experiment_test.go](./bloom_store_experiment_test.go) |
| Counter 指标族名称歧义、独立 Metadata 请求 | [protocol_test.go](./protocolcheck/protocol_test.go) |
| 回归检查 | `make test` 写入 `results/split_tests.txt` |

- *[1] ExportJSONFunc 将 JSON 数据交给内存接收函数，真实 ExportFunc 须响应 context 取消。*

## 0x04 实现边界

原型在 BloomStore 中合并存储与发送，保留为选型对照。生产 Store／Exporter 使用双 Bloom、按主键防抖和准入配额，测试见 [实现验收](../PLAN.md#0x06-验收与验证)，原型结果不代表生产模块。

## 0x05 集群发压

[loadgen](./cmd/loadgen/main.go) 在 operator Pod 中向 collector 发送 OTLP 指标，同时读取目标 collector 的 `/metrics`。配置从 stdin 读取，Token 不写入结果。

```bash
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o loadgen ./cmd/loadgen
```

输入结构：

```json
{
  "Target": "http://<collector-pod-ip>:4318",
  "Admin": "http://<collector-pod-ip>:4310",
  "Token": "<APM_TOKEN>",
  "Service": "metricmeta-scale",
  "Group": "metadata-benchmark",
  "Services": 10,
  "Groups": 10,
  "Mode": "steady",
  "Metrics": 1000,
  "RPS": 100,
  "Seconds": 1320,
  "Warmup": 1080,
  "ScrapeSeconds": 30,
  "DataID": 1001
}
```

`Services × Groups × Metrics` 为元信息主键数，单次请求携带一个服务／分组的 `Metrics` 个指标。服务和分组按请求轮转，样本为 `10` 服务 × `10` 分组 × `1,000` 指标，共 `100,000` 个主键。

`Seconds` 包含预热；请求统计和资源统计排除 `Warmup`。`steady` 保持描述不变，`churn` 每次请求变更描述。默认防抖验证使用 `1` 个指标持续变更 `660 s`，停止后再等待稳定窗口；DataID 配额验证使用 `1,000` 个指标持续变更。

输出包含目标／实际 QPS、HTTP 状态、部分接收、P99、CPU、RSS、按 `ScrapeSeconds` 采样的资源和元信息计数。`DataID` 用于筛选出口点与处理链路丢弃计数；接收预检失败按输入 Token 筛选，输出不保留 Token 标签。HTTP 成功只证明入口接收，数值指标与 info 的入库结果须按服务和分组另行查询。

容量阶梯保持每个指标每秒一个点，即 `RPS = Services × Groups`；比较开启和关闭时保持负载与采样周期一致。性能结果见 [基准压测](../PLAN.md#0x07-基准压测)。

完整元信息覆盖按 `(scope, metric)` 在预热与测量全窗口内去重累计。info 默认只保留两分钟，瞬时条目数不等于本轮已发布的主键总数；入库覆盖需用历史窗口核对。
