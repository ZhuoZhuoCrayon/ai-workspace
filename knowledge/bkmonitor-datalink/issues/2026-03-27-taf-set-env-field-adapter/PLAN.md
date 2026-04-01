---
title: Taf 服务上报适配环境字段 —— 实施方案
tags: [taf, tars, set, converter, apm]
issue: ./README.md
description: 从 Taf 服务名中分离 set 段，写入独立环境维度，保持服务名纯净
created: 2026-03-27
updated: 2026-03-27
---

# Taf 服务上报适配环境字段 —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 核心思路

`statHeadToDims` 和 `propHeadToDims` 是唯二的维度建模入口，下游三条路径（原始指标、聚合指标、Server 视角衍生）都从同一个 dims map 起始。只需在这两个入口做一次解析，即可全局生效。

引入 `parseTafServiceName`，将现有的 `tokenparser.FromString` + `splitAtLastOnce("@")` 合并为一步，同时提取纯净服务名、set 段和版本号。

约束：服务名格式不固定（可能是 `App.Server`，也可能是 `stat_from_server` 等非标格式），set 段分离需用安全的字符串启发式，无法识别时保持原样不剥离。

## 0x02 新增字段

| 维度键 | 语义 | 取值 |
|--------|------|------|
| `region` | 本服务侧 SetID（与 `service_name` 对称：client 取主调 set，server 取被调 set） | MasterName / SlaveName 中分离出的 set 段 |
| `caller_con_setid` | 主调 SetID（始终填充，不随角色变化） | MasterName 中分离出的 set 段 |
| `callee_con_setid` | 被调 SetID（始终填充，不随角色变化） | SlaveName 中分离出的 set 段 |

新字段参与聚合 PK，不同 set 分开统计。

## 0x03 改造范围

- **`statHeadToDims`**：替换解析链为 `parseTafServiceName`，dims map 新增三个字段，按角色选取 `region`
- **`propHeadToDims`**：同上，新增 `region`
- **`handleStat` Server 视角衍生**：`MergeMapWith` 追加覆写 `region` 为 `callee_con_setid`
- **`tars_test.go`**：补充 `parseTafServiceName` 表驱动测试，更新现有 fixture 预期维度

## 0x04 Server 视角衍生开关

`handleStat` 中主调转被调视角的衍生逻辑改为可配置。

`TarsConfig` 新增 `IsDeriveServerView`（`is_derive_server_view`），与 `IsDropOriginal` 风格一致，零值 `false` = 功能默认关闭。

- **`config.go`**：`TarsConfig` 新增 `IsDeriveServerView bool` 字段
- **`handleStat`**：`if role == statTagRoleClient {` 改为 `if role == statTagRoleClient && c.conf.IsDeriveServerView {`
- **`tars_test.go`**：新增 `TestTarsStatServerViewDeriveDisabled`，验证关闭时只产出 client event

---
*制定日期：2026-03-27*
