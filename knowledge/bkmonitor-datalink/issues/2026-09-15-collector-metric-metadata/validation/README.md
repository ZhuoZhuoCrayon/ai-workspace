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
| Counter 指标族名称称歧义、独立 Metadata 请求 | [protocol_test.go](./protocolcheck/protocol_test.go) |
| 回归检查 | `make test` 写入 `results/split_tests.txt` |

- *[1] ExportJSONFunc 将 JSON 数据交给内存接收函数，真实 ExportFunc 须响应 context 取消。*

## 0x04 实现边界

原型在 BloomStore 中合并存储与发送，保留为选型对照。生产 Store／Exporter 使用双 Bloom、按主键防抖和准入配额，测试与发布依赖见 [实现验收](../PLAN.md#0x06-验收与验证)，原型结果不代表生产模块。
