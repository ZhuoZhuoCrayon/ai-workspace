# bk-collector 1c1g Adaptive Throttle 候选参数搜索报告

## 0x01 结论

本报告只回答一个问题：哪组参数值得进入集群 `-d 240s` 压测。

本地搜索的结论是：

- CPU 限流可以独立生效。CPU-only 阶段把 `mem_hard` 设为 `10.0`，`Open=0` 但 `Shedding=23`，说明请求不是被内存硬熔断挡住的。
- 候选 CPU 参数是 `cpu_enter=0.95`、`cpu_exit=0.85`、`cpu_hard=1.50`、`drop_max=0.20`。
- `mem_hard=0.95` 适合作为下一轮验证的兜底阈值。它比 `0.92` 更少进入 `Open`，比 `0.96` 在高压下少拒绝。
- 这不是 240s 稳定性结论。搜索阶段 `-d 8s`，复验阶段 `-d 12s`，只能用于筛参数，不能替代集群长压。

推荐进入 C 场景的配置：

```yaml
receiver:
  throttle:
    enabled: true
    sample_interval: 250ms
    signal:
      cpu_slow_beta: 0.95
      cpu_fast_beta: 0.70
      fallback_cores: 1
    thresholds:
      cpu_enter: 0.95
      cpu_exit: 0.85
      cpu_hard: 1.50
      mem_hard: 0.95
      breach_n: 3
    rules:
      default:
        drop_min: 0.00
        drop_max: 0.20
      metrics:
        enabled: false
```

## 0x02 实验边界

本地实验刻意做得短，目的是快速筛掉明显不合适的参数。

| 项目 | 口径 |
| --- | --- |
| 运行环境 | OrbStack / Docker linux arm64 |
| collector 配额 | `1c1g` |
| 压测工具 | `pkg/collector/dist/loadgen-throttle-darwin-arm64` |
| 压力档位 | `-c 26`、`32`、`40`、`48`、`64` |
| 搜索时长 | `-d 8s`，三阶段合计 `24s` |
| 复验时长 | `-d 12s`，三阶段合计 `36s` |
| 采样方式 | 每 `1s` 抓取 collector `/metrics` |
| CPU-only 处理 | `mem_hard=10.0`，等效关闭内存熔断 |

两个边界必须提前看清：

- 本地 loadgen 的阶段 Span 固定为 `warmup=32`、`burst=128`、`bigpayload=512`。集群压测命令使用 `warmup=128`、`burst=512`、`bigpayload=128`，两边的绝对吞吐不能直接对齐。
- 本地复验只说明候选参数有价值。最终能不能扛住，要看集群 `-d 240s` 的 OOM、重启、`other` 和延迟。

## 0x03 判定口径

| 指标 | 含义 |
| --- | --- |
| 成功 Span | `200` 请求携带的 Span 总数 |
| 429 请求 | throttle 主动拒绝的请求数 |
| other 请求 | 连接拒绝、reset、EOF、timeout 等非 HTTP 成功响应 |
| Shedding 样本 | throttle 进入概率丢弃状态的采样数 |
| Open 样本 | throttle 进入硬保护状态的采样数 |
| Max mem/limit | 采样窗口内内存使用率峰值，按 limit 归一化 |
| OOM | 容器是否出现 OOMKilled 或异常退出 |

排序原则：先排除 OOM，再看成功 Span；成功 Span 接近时，优先选 429、other、Open 更少的参数。

## 0x04 CPU-only 搜索

CPU-only 搜索用 `mem_hard=10.0`，避免内存熔断提前接管。

| 参数组 | 说明 | 成功 Span | 429 请求 | Open 样本 | Shedding 样本 | OOM |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `cpu_e095_dm20_h150` | `cpu_enter=0.95`、`drop_max=0.20`、`cpu_hard=1.50` | 443,520 | 3 | 0 | 23 | 0 |
| `cpu_e090_dm20_h150` | `cpu_enter=0.90`、`drop_max=0.20`、`cpu_hard=1.50` | 441,984 | 23 | 1 | 29 | 0 |
| `cpu_e090_dm10_h150` | `cpu_enter=0.90`、`drop_max=0.10`、`cpu_hard=1.50` | 441,280 | 352 | 0 | 32 | 0 |
| `cpu_e100_dm20_h150` | `cpu_enter=1.00`、`drop_max=0.20`、`cpu_hard=1.50` | 440,480 | 4 | 0 | 13 | 0 |
| `cpu_e105_dm20_h150` | `cpu_enter=1.05`、`drop_max=0.20`、`cpu_hard=1.50` | 431,808 | 0 | 0 | 1 | 0 |

结论：

- `cpu_e095_dm20_h150` 是本地 CPU-only 搜索的第一候选。它成功 Span 最高，429 只有 `3`，没有进入 `Open`。
- `Shedding=23` 是关键证据：这组参数在内存熔断关闭时仍然开始降载。
- `cpu_enter=1.05` 几乎不降载，保护偏晚；`cpu_enter=0.75～0.85` 更保守，但成功 Span 明显下降。

## 0x05 mem_hard 搜索

在 CPU-only 第一候选上复验 `mem_hard`。

| mem_hard | 成功 Span | 总失败率 | c26 失败率 | c64 失败率 | Open 样本 | OOM | 结论 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `0.92` | 700,864 | 4.82% | 1.93% | 7.82% | 16 | 0 | 吞吐略高，但更早进入 `Open`。 |
| `0.95` | 687,904 | 4.77% | 0.61% | 8.02% | 10 | 0 | 推荐进入集群验证。 |
| `0.96` | 681,408 | 9.20% | 1.01% | 15.71% | 8 | 0 | 高压拒绝明显变多。 |

为什么选 `0.95`：

- `0.92` 的成功 Span 更高，但 `Open` 样本更多，低压 `c=26` 下也有更多失败。
- `0.96` 在 `c=64` 下失败率升到 `15.71%`，说明阈值偏晚，压力已经转成大量拒绝和连接异常。
- `0.95` 不是吞吐最高的一组，但低压更干净，高压也没有明显恶化。它更适合做集群 C 场景候选。

## 0x06 下一轮集群验证

C 场景先跑和 A 相同的压力：

```bash
./loadgen-linux-amd64 \
  -url "http://bkm-collector.bkmonitor-operator:4318/v1/traces" \
  -token "<token>" \
  -c 26 \
  -d 240s \
  -warmup-spans 128 \
  -burst-spans 512 \
  -bigpayload-spans 128
```

验证重点：

- `bk_collector_throttle_state` 应先出现 `Shedding=1`，不应主要靠 `Open=2` 扛压。
- `bk_collector_throttle_water_level{kind="cpu_slow"}` 应越过 `cpu_enter=0.95`。
- `bk_collector_throttle_water_level{kind="mem"}` 不应长期贴近 `mem_hard=0.95`。
- loadgen 的 `other` 应为 `0` 或接近 `0`。
- Pod 不应出现 OOMKilled，collector uptime 不应重置。

如果 `-c 26` 无 OOM 且 `other` 可控，再升到 `-c 28`。不建议直接跳到 `-c 32`，前面的集群压测已经在该压力下出现连接拒绝、reset 和 timeout。

## 0x07 风险

- CPU-only 阶段多组实验的 `Max mem/limit` 接近 `1.000`。CPU 限流能提前降载，但不能替代内存保命线。
- 本地搜索时间太短，无法覆盖长时间堆积、GC 周期、Pod 重启恢复和上游重试。
- `c=64` 在本地复验中多次出现 `other`，只能当过载边界，不适合作为容量目标。

## 0x08 实验产物

| 产物 | 路径 |
| --- | --- |
| 实验脚本 | `bkmonitor-files/collector-throttle-lab/search_runner.py` |
| 系统搜索汇总 | `bkmonitor-files/collector-throttle-lab/run-20260621-systematic/summary.json` |
| 补充搜索汇总 | `bkmonitor-files/collector-throttle-lab/run-20260621-supplement/summary.json` |
| `mem_hard=0.96` 复验 | `bkmonitor-files/collector-throttle-lab/run-20260621-mem096/summary.json` |
