---
title: collector 空资源维度占位排查
tags: [collector, apm, resource, k8s, fill-dimensions, troubleshooting]
description: SDK 上报空资源字段时，collector 补维度只按 key 存在判断，导致 from_record 和 from_cache 跳过有效兜底
created: 2026-06-25
updated: 2026-06-26
---

# collector 空资源维度占位排查

## 0x01 现象

某 APM 应用在 `mock-cluster` 上出现 K8s 维度缺失：Java OTel SDK `1.24.0` 上报的业务 span 没有 `k8s.*` 字段，同集群其他 SDK 的服务正常。

问题不在缓存。operator `/pods` 能返回 `<mock-pod-ip> -> mock-java-app-0` 的映射，collector 也在持续处理 traces。第一处断点更靠前：Java SDK 已经把 `resource.net.host.ip` 写成空字符串。

Java Resource 的关键字段如下：

```text
resource.net.host.ip            = ""
resource.net.host.name          = "mock-java-app-0.mock-ns"
resource.telemetry.sdk.language = "java"
```

平台下发的 `resource_filter/fill_dimensions` 只有两步：

1. `from_record` 把 `request.client.ip` 写到 `resource.net.host.ip`。
2. `from_cache` 用 `resource.net.host.ip` 查 `k8s_cache`，补齐 `k8s.namespace.name`、`k8s.pod.name`、`k8s.pod.ip` 和 `k8s.bcs.cluster.id`。

第一步没有写进去，第二步只能拿空字符串查缓存。`k8s.*` 维度因此断在 `from_cache` 之前。

还有一个同类问题：Span 里如果已经带了空的 `resource.k8s.bcs.cluster.id`，`from_cache` 即使查到缓存，也不会把缓存里的集群 ID 写回去。

## 0x02 根因

`from_record` 和 `from_cache` 都使用 OTel pdata 的 `InsertString` 写目标字段。这个 API 只看 key 是否存在，不看值是否为空：目标 key 已存在时不会写入新值。

空字符串卡住了两类补齐动作：

1. `net.host.ip=""` 会让 `from_record` 跳过 `request.client.ip`，后续 `from_cache` 只能拿空字符串查 Pod。
2. `k8s.bcs.cluster.id=""` 会让 `from_cache` 跳过缓存值，字段最后仍然是空串。

根因链路：

```mermaid
flowchart TD
    A["SDK 上报空资源字段"] --> B{"空串位置"}
    B -- "net.host.ip" --> C["from_record 跳过 request.client.ip"]
    C --> D["from_cache 查询空字符串"]
    B -- "k8s.*" --> E["from_cache 命中缓存"]
    E --> F["InsertString 跳过缓存维度"]
    D --> G["K8s 维度缺失"]
    F --> H["K8s 维度仍为空"]
```

## 0x03 排查过程

1. 对比同集群不同 SDK 的 span：Java SDK 缺 `k8s.*`，其他 SDK 正常。
2. 核对 operator `/pods` 和 collector 状态：mock Pod 映射存在，collector traces pipeline 有持续计数。
3. 读取平台配置：`get_resource_fill_dimensions_config` 使用 `from_record -> from_cache` 串起请求 IP 和 `k8s_cache`。
4. 读取 collector 实现：`fromRecordAction` 对 `request.client.ip` 调用 `InsertString`。
5. 对照同文件 `defaultValueAction`：默认值动作已经把 `!ok || v.AsString() == ""` 视为空位，再用 `Upsert*` 写入。
6. 复查同类写入点：`fromCacheAction` 写缓存维度时也调用 `InsertString`，空 `k8s.*` 目标会挡住缓存结果。

结论：补资源维度的空位判断过窄，把“key 存在”误当成“字段可用”。

## 0x04 解决方案

把补资源维度的写入协议改成：来源非空，且目标缺失或为空时写入。目标已有非空值时保持现值。

实现方式是在 `pkg/collector/processor/resourcefilter/factory.go` 收敛一个包内私有函数：

```go
func upsertStringIfMissingOrEmpty(attrs pcommon.Map, key, value string) {
	if value == "" {
		return
	}
	if current, ok := attrs.Get(key); ok && current.AsString() != "" {
		return
	}
	attrs.UpsertString(key, value)
}
```

改动范围：

| 对象 | 处理方式 | 目标 |
| --- | --- | --- |
| `fromRecordAction` | `request.client.ip` 分支调用 `upsertStringIfMissingOrEmpty` | 修复空 `net.host.ip` 挡住请求 IP 的问题 |
| `fromCacheAction` 查询 key | 空字符串直接跳过，继续尝试下一个组合 key | 避免空 lookup key 误占一次缓存查询 |
| `fromCacheAction` 缓存维度 | 缓存结果调用 `upsertStringIfMissingOrEmpty` 写回 | 修复空 `k8s.*` 目标挡住缓存值的问题 |
| 其他 `from_*` 动作 | 保持 `InsertString` | 不把 metadata、token 的写入语义混进这条 K8s 补维度链路 |

## 0x05 注意事项与回归点

- 不做空白字符归一化；`" "` 是否应视为空，留给后续数据清洗规则判断。
- `record.RequestClient.IP` 为空时不新建空目标字段，已存在的目标字段也不被清空。
- `from_cache` 查缓存时跳过空 key；如果后续组合 key 还有有效值，会继续尝试后面的 key。
- 已有非空 `k8s.*` 维度不被缓存覆盖。
- 新增 `TestFromRecordActionEmptyFallback`，覆盖 traces、metrics、logs 三类 `RecordType`。
- 扩展 `TestFromCacheAction`，覆盖空 `k8s.bcs.cluster.id` 回填和空查询 key 跳过。

核心用例：

| 场景 | 输入 | 期望 |
| --- | --- | --- |
| `from_record` 目标缺失或为空 | `RequestClient.IP=<mock-pod-ip>` | 写入 `<mock-pod-ip>` |
| `from_record` 目标已有非空值 | `net.host.ip=<mock-existing-ip>` | 保持 `<mock-existing-ip>` |
| `from_record` 来源为空 | `RequestClient.IP=""` | 不新建空字段 |
| `from_cache` 目标为空 | `k8s.bcs.cluster.id=""`，缓存有集群 ID | 写入缓存集群 ID |
| `from_cache` 目标已有非空值 | `k8s.pod.name=existing-pod` | 保持 `existing-pod` |
| `from_cache` 查询 key 为空 | `net.host.ip=""`，`client.ip=<mock-pod-ip>` | 跳过空 key，使用 `client.ip` 命中缓存 |

回归门禁：

```bash
cd /Users/sandrincai/Project/Github/bk/bkmonitor-datalink/pkg/collector
source "$HOME/.gvm/scripts/gvm" && gvm use go1.23.0
go test ./processor/resourcefilter/...
```

## 0x06 参考

- [<源码> bkmonitor-datalink/resourcefilter fromRecordAction](https://github.com/TencentBlueKing/bkmonitor-datalink/blob/master/pkg/collector/processor/resourcefilter/factory.go#L348-L382)
- [<源码> bkmonitor-datalink/resourcefilter defaultValueAction](https://github.com/TencentBlueKing/bkmonitor-datalink/blob/master/pkg/collector/processor/resourcefilter/factory.go#L443-L456)
- [<源码> bkmonitor get_resource_fill_dimensions_config](https://github.com/TencentBlueKing/bk-monitor/blob/master/bkmonitor/apm/core/platform_config.py#L332-L380)
- [<源码> bkmonitor get_resource_filter_config_metrics](https://github.com/TencentBlueKing/bk-monitor/blob/master/bkmonitor/apm/core/application_config.py#L430-L460)
