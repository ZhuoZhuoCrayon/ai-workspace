---
title: Taf 服务上报适配环境字段
tags: [taf, tars, set, converter, apm]
description: Taf 上报在 EnableSet 场景下，将 set 段从服务名中分离，填充到独立的环境字段
created: 2026-03-27
updated: 2026-03-27
---

# Taf 服务上报适配环境字段

## 0x01 背景

### a. Why

Taf 上报在 EnableSet 场景下，主被调服务名后会拼接 set 相关信息，导致服务名中混入环境标识：

| 场景 | 服务名示例 |
|------|-----------|
| 禁用 set | `Hello.World` |
| 禁用 set，启用版本 | `Hello.World@1.1` |
| 启用 set | `Hello.World.devsh*` |
| 启用 set，启用版本 | `Hello.World.devsh*@1.1` |

需要将 set 段从服务名中分离，填充到独立的环境字段，保持服务名纯净。

### b. 目标

- 从主调服务（master）分离 set 段，写入 `caller_con_setid`（主调 SetID）
- 从被调服务（slave）分离 set 段，写入 `callee_con_setid`（被调 SetID）
- 本服务侧的 setid（主调指标中的主调服务 / 被调指标中的被调服务）写入 `resourceTagRegion`（`region`）字段，类似 `resourceTagServiceName` 的处理方式

## 0x02 实现路线

### a. 建议的方案

改动位置：

- stat 转换：`pkg/collector/exporter/converter/tars.go:173`
- prop 转换：`pkg/collector/exporter/converter/tars.go:219`

### b. 约束

- 需兼容所有四种服务名格式（有无 set、有无版本号）
- 分离后的服务名应去除 set 和版本后缀，恢复为 `App.Server` 形式

## 0x03 参考

Taf（Tars）框架指标上报逻辑（Go SDK）：

**客户端上报**（`ReportStatFromClient`）：
- EnableSet 场景下，MasterName 格式为 `App.Server.SetName+SetArea+SetID@Version`
- 被调侧若有 SetId，SlaveName 格式为 `App.Server.SetName+SetArea+SetID`

```go
// EnableSet 场景下主调服务名拼接
head.MasterName = fmt.Sprintf("%s.%s.%s%s%s@%s", sCfg.App, sCfg.Server, setList[0], setList[1], setList[2], sCfg.Version)

// 被调侧有 SetId 时
head.SlaveName = fmt.Sprintf("%s.%s.%s%s%s", sNames[0], sNames[1], setList[0], setList[1], setList[2])
```

**服务端上报**（`ReportStatFromServer`）：
- EnableSet 场景下，SlaveName 格式为 `App.Server.SetName+SetArea+SetID`
- 同时设置 SlaveSetName / SlaveSetArea / SlaveSetID 字段

```go
// EnableSet 场景下被调服务名拼接
head.SlaveName = fmt.Sprintf("%s.%s.%s%s%s", cfg.App, cfg.Server, setList[0], setList[1], setList[2])
head.SlaveSetName = setList[0]
head.SlaveSetArea = setList[1]
head.SlaveSetID = setList[2]
```
