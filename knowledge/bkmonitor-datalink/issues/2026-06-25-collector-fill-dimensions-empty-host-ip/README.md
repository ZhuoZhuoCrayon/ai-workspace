---
title: bk-collector net.host.ip 兜底被空值占位
tags: [collector, apm, resource, k8s, fill-dimensions]
description: SDK 写入空 net.host.ip 时 from_record 不覆盖，导致 k8s.* 全套维度补全失效
created: 2026-06-25
updated: 2026-06-25
---

# bk-collector net.host.ip 兜底被空值占位

## 0x01 背景

### a. Why

集群 `BCS-K8S-26932` 内 Java OTel SDK（`1.24.0`）上报的业务 span 拿不到 K8s 关联维度，`k8s.bcs.cluster.id`、`k8s.namespace.name`、`k8s.pod.name`、`k8s.pod.ip` 四个字段集体缺失。同集群里 Go / galileo SDK 的服务 span 正常补齐，问题只在 Java SDK 上复现。

逐层排查到的事实：

| 检查项 | 现状 |
| --- | --- |
| `resource_filter/fill_dimensions` 与 `k8s_cache` | 已下发，`traces_pipeline` 里位于 `instance_id` 之前 |
| operator `/pods` 接口 | 返回 `11.166.167.30 → letsgo-metro-activity-game-svr-0` 的映射 |
| collector 健康状态 | healthz `200`、cache 同步无错、traces pipeline 计数持续增长 |

差异落在 Java SDK 上报的 Resource：

```text
resource.net.host.ip            = ""                                          ← 空字符串，但 key 存在
resource.net.host.name          = "letsgo-metro-activity-game-svr-0.gamesvr"
resource.telemetry.sdk.language = "java"
```

`fill_dimensions.from_record` 用 OTel pdata 的 `InsertString` 写入 `net.host.ip`，语义是「key 存在就跳过」。空字符串也算存在，SDK 写的 `""` 把 collector 的兜底位置占住了。下一步 `from_cache` 拿这个空字符串去查 `k8s_cache`，必然查不到，整条 `k8s.*` 维度跟着丢。

### b. 目标

- `from_record` 在目标 key 缺失或现值为空时都能正确兜底写入
- 现值非空仍尊重 SDK，「补全而非覆盖」不破
- 既有用例不回归，新增单元测试覆盖空值兜底

## 0x02 实现路线

### a. 建议的方案

把 `from_record` 的判定条件从「key 不存在才写」放宽到「key 不存在 或 现值为空字符串」，让 SDK 写的空字符串不再压住 collector 的兜底。

### b. 约束

- 改动只覆盖 `from_record`，`from_cache`、`from_metadata`、`from_token` 的同类空值占位风险作为后续事项独立评估
- 不引入无条件覆盖语义，SDK 写非空值仍要尊重
- 只处理字面空字符串，不识别空白、`null` 等变体

## 0x03 参考

- 触发现场：APM 应用 `red_test`（`bk_biz_id=101003`），业务 Pod `letsgo-metro-activity-game-svr-0`
- 代码位置：[<源码> resourcefilter/factory.go fromRecordAction](https://github.com/TencentBlueKing/bkmonitor-datalink/blob/master/pkg/collector/processor/resourcefilter/factory.go#L348-L382)
- 配置入口：[<源码> apm/core/platform_config.py get_resource_fill_dimensions_config](https://github.com/TencentBlueKing/bk-monitor/blob/master/bkmonitor/apm/core/platform_config.py#L332-L380)
