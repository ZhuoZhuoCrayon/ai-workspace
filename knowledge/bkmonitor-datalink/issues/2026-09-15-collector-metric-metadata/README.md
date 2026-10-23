---
title: bk-collector 指标元信息采集与同步
tags: [collector, metrics, metadata, otlp, remote-write]
description: 在指标语义丢失前提取元信息，按隔离范围聚合并减少重复同步
created: 2026-09-15
updated: 2026-10-23
---

# bk-collector 指标元信息采集与同步

## 0x01 背景

### a. Why

collector 将不同协议转换为数值指标时，会丢失描述、单位和聚合语义。消费端只能猜测同名指标的含义，Histogram 的拆分指标也难以对应回原始指标。

同一 DataID 下的服务或分组可以定义同名指标，元信息必须按范围隔离。逐数据点同步会放大写入量，需要按主键合并并周期去重，collector 与其他采集器复用同一协议。

### b. 目标

- 明确 OTLP、Tars、OTP 和 Prometheus Remote Write 的元信息来源与采集位置。
- 在 `pkg/utils/metricmeta` 实现 Scope、Store 与 Exporter，提供 Start／Stop、Clean 和使用方注入的 ExportFunc。
- 对持续变化、异常 DataID 和发送失败提供有界防御，并用 Go 测试和真实 HTTP 请求验证。

## 0x02 实现路线

### a. 选定方案

待发缓冲（pending）保存每个主键的最新候选，成功版本用双 Bloom 去重，默认总误判率为 `1e-6`。每 `1 h` 轮换一代，版本保留 `1 h～2 h`，通过持续观察重报；防抖、黑名单和全局／DataID 配额限制异常更新。

OTP 描述随 Record 传递，在 exporter 绑定身份并登记；OTLP、Tars、Pushgateway 在各自 converter 提取。原生 Remote Write v1 的独立 Metadata 缺少可靠的实际序列绑定，暂不登记元信息。

| 阅读目的 | 入口 |
| --- | --- |
| 看选型与内存代价 | [PLAN：调研与约束](./PLAN.md#0x01-调研与约束)和[性能结果](./PLAN.md#b-性能结果) |
| 看通用结构与调用接口 | [PLAN：架构设计](./PLAN.md#0x02-架构设计)和[接入与生命周期](./PLAN.md#a-接入与生命周期) |
| 看 collector 接入位置 | [PLAN：开发方案](./PLAN.md#0x04-开发方案) |
| 验收实现与发布依赖 | [PLAN：验收与验证](./PLAN.md#0x06-验收与验证) |
| 核查协议、源码和实验数据 | [REPORT](./REPORT.md) |
| 运行 demo 与压测 | [Go 实验工程](./validation/README.md) |

### b. 约束

生产模块和 collector 本地适配通过测试；发布依赖 utils 发版、OTP 独立源码同步及实际接收服务联调，见 [发布依赖](./PLAN.md#c-发布依赖)。

- 主键为 `dataid + __scope_type + __scope + __metric`，需求中的 `__scope_name` 统一为 `__scope`。
- utils 预定义 APM／PLUGIN／DEFAULT，允许使用方扩展类型和范围，collector 的 APM 路径使用最终 service_name 与 scope_name 编码。
- ExportFunc 的发送目标由使用方决定。
- 持续观测的未变更元信息也必须周期重发，内存缓存不提供进程重启后的补发保证。
- 允许极低概率遗漏，一次性指标可能无法补回，历史值回退可能等待强制补报。

## 0x03 参考

需求来源：`【2026】📝 自定义指标开箱即用调研.docx`。本方案覆盖 collector 的元信息采集与同步，下游存储、展示和产品排期由对应方案定义。

结构参考：[collector 自适应限流方案](../2026-06-10-collector-adaptive-throttling/PLAN.md)和[对应调研](../2026-06-10-collector-adaptive-throttling/PREPLAN.md)。协议与源码证据集中在 [REPORT](./REPORT.md)。
