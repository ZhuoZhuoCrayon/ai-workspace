---
title: 采集器抓包常用命令
tags: [collector, tcpdump, packet-capture, pcap]
description: 记录采集器排障时常用的 tcpdump 抓包命令，以及关键参数含义
created: 2026-04-10
updated: 2026-04-10
---

# 采集器抓包常用命令

## 0x01 关键信息

### a. 适用场景

- 需要在终端里直接查看采集器相关流量内容。
- 需要把抓到的包保存成 `pcap` 文件，供后续离线分析。

### b. 常用命令

```bash
tcpdump -nn -A -s 0 -i any 'tcp port 4318'
```

```bash
tcpdump -nn -s 0 -i any -w otlp-http-4318.pcap 'tcp port 4318'
```

### c. 参数含义

- `-nn`：不解析主机名和端口名，输出更直接。
- `-A`：按 ASCII 打印抓到的内容，适合直接看 HTTP 头和部分文本内容。
- `-s 0`：抓完整包，不截断。
- `-i any`：监听所有网卡，适合先做全局排查。
- `-w <file>`：将原始抓包保存为 `pcap` 文件。
- `'tcp port 4318'`：只抓 `4318` 端口的 TCP 流量；若排查其他端口，替换即可。

## 0x02 说明

- 第一条命令用于终端直接看内容。
- 第二条命令用于保存抓包文件，便于后续用 Wireshark、tshark 等工具离线分析。
- 若只想看请求方向，可将过滤条件改成 `'tcp dst port 4318'`。

## 0x03 参考

- [tcpdump man page](https://www.tcpdump.org/manpages/tcpdump.1.html)
