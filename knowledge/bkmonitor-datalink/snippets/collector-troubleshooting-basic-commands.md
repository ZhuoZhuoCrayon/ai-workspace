---
title: 采集器排障常用命令
tags: [collector, tcpdump, packet-capture, pcap, otlp, traces]
description: 记录采集器排障时常用的 tcpdump 抓包与 OTLP HTTP traces 探针命令，以及关键参数含义
language: bash
created: 2026-04-10
updated: 2026-06-28
---

# 采集器排障常用命令

## 0x01 关键信息

### a. 适用场景

- 终端里直接查看采集器相关流量内容。
- 把抓到的包保存成 `pcap` 文件，供后续离线分析。
- 在业务 Pod 内手工发一条 OTLP HTTP traces，验证 collector 受理与 `fill_dimensions` 行为。

## 0x02 代码片段

### a. 抓包

终端直接看流量：

```bash
tcpdump -nn -A -s 0 -i any 'tcp port 4318'
```

保存为 pcap 文件供 Wireshark / tshark 离线分析：

```bash
tcpdump -nn -s 0 -i any -w otlp-http-4318.pcap 'tcp port 4318'
```

- `-nn` 不解析主机名和端口名。
- `-A` 按 ASCII 打印，适合直接看 HTTP 头和文本内容。
- `-s 0` 抓完整包不截断。
- `-i any` 监听所有网卡。
- `-w <file>` 保存为 `pcap`。
- `'tcp port 4318'` 只抓 `4318` 端口；改 `'tcp dst port 4318'` 只看请求方向，端口可换成其他业务端口。

### b. OTLP HTTP traces 探针（busybox 兼容）

业务 Pod 内构造一条最小化 OTLP HTTP span 发到本集群 collector：

```bash
COLLECTOR_URL="http://bkm-collector.bkmonitor-operator:4318/v1/traces"
BK_TOKEN="<目标 APM 应用的写入 token>"

NOW_S=$(date +%s)
NOW_NS=$((NOW_S * 1000000000))
END_NS=$((NOW_NS + 1000000000))
HOST="$(hostname)"
TRACE_ID="aaaaaaaaaaaaaaaa$(head -c 8 /dev/urandom | xxd -p)"
SPAN_ID=$(head -c 8 /dev/urandom | xxd -p)

REQ_BODY=$(cat <<EOF
{
  "resourceSpans": [{
    "resource": {"attributes": [
      {"key": "service.name",           "value": {"stringValue": "diag-empty-hostip"}},
      {"key": "net.host.ip",            "value": {"stringValue": ""}},
      {"key": "net.host.name",          "value": {"stringValue": "$HOST"}},
      {"key": "telemetry.sdk.language", "value": {"stringValue": "java"}},
      {"key": "telemetry.sdk.name",     "value": {"stringValue": "opentelemetry"}},
      {"key": "telemetry.sdk.version",  "value": {"stringValue": "1.24.0"}}
    ]},
    "scopeSpans": [{
      "scope": {"name": "diag", "version": "1.0.0"},
      "spans": [{
        "traceId": "$TRACE_ID", "spanId": "$SPAN_ID",
        "name": "diag.empty-net-host-ip", "kind": 1,
        "startTimeUnixNano": "$NOW_NS", "endTimeUnixNano": "$END_NS",
        "status": {"code": 1}
      }]
    }]
  }]
}
EOF
)

echo "TRACE_ID=$TRACE_ID"
echo "NOW_NS=$NOW_NS  END_NS=$END_NS"
curl -i -X POST "$COLLECTOR_URL" \
  -H 'Content-Type: application/json' \
  -H "X-BK-TOKEN: $BK_TOKEN" \
  -d "$REQ_BODY"
```

- **busybox `date` 不支持 `%N`**：`$(date +%s%N)` 在 busybox / distroless busybox 上会原样输出 `N`（如 `1782652397N`），receiver 收到非法 timestamp，HTTP 仍可能 `200`，但下游 transfer / ES 索引时静默丢弃。脚本统一用 `date +%s` 拼 9 个 `0` 做秒级精度，跨发行版可用。
- **`kind: 1`** 是 `SPAN_KIND_INTERNAL`，最小化业务语义依赖；要测 server / client 行为时改 `2` / `3`。

## 0x03 参考

- [tcpdump man page](https://www.tcpdump.org/manpages/tcpdump.1.html)
- [OpenTelemetry Protocol HTTP encoding](https://opentelemetry.io/docs/specs/otlp/#otlphttp)
