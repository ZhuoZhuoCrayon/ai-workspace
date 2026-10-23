---
title: APM 日志存储集群切换方案
tags: [apm, log, storage, frontend]
issue: ./README.md
description: 用现有日志存储协议补齐集群选择和刷新，后端不新增接口
created: 2026-10-23
updated: 2026-10-23
---

# APM 日志存储集群切换方案

## 0x01 调研与设计

**缺口在前端入口，日志存储配置仍由既有更新链路管理。**

- 日志页 `storage-state-log.tsx` 已收到 `clusterList`，但集群字段设置了 `showEditable=false`。
- `SetupResource.LogDatasourceSetProcessor` 接收 `log_datasource_option`，`LogDataSource.apply_datasource` 将集群 ID 传给日志平台 `CollectorHandler.custom_update`。
- 父组件 `logStorageChange` 只合并参数，不能刷新服务端派生的集群名和物理索引。

```text
Log → setup(log_datasource_option) → LogDataSource → update_custom_report
    ← 保存成功后：storageInfo + indicesInfo
```

## 0x02 最小开发方案

| 责任 | 改动 |
| --- | --- |
| 选择与校验 | 日志页复用 `EditableFormItem` 选择器与现有可见 ES 列表，按目标集群校验保留天数、分片数和副本数，保留应用管理权限控制 |
| 提交 | 复制现有完整 `es_*` 参数，仅替换 `es_storage_cluster`，保留 `0` 副本，不静默改默认值 |
| 回显 | 父级保存成功后重新拉取存储信息和物理索引，失败保留原状态 |

确认框展示源/目标集群和保留天数，说明历史数据仍可查询、按生效保留策略清理，与关联文案需求共用口径。
改动集中于日志页、父级存储页和必要的国际化资源，不新增接口、迁移任务或公共抽象。
范围限于 APM 管理的 OTLP 日志 ES → ES 切换，关联外部日志索引及 ES/Doris 互切不纳入本需求。

## 0x03 验收与验证

- 有权限可选择可见集群，超限、无目标及取消均不提交，保留原过期时间编辑能力。
- 保存后集群名、保留天数及物理索引刷新正确，失败不产生成功回显，Trace 配置不受影响。
- 用测试应用验证新旧日志及跨切换时间查询、历史数据到期清理，不能以源码核对代替无损切换验收。

## 0x04 实施进展

| 时间 | 结论性进展 |
| --- | --- |
| 2026-10-23 16:00 | 完成源码调研与最小方案，已建单并排期，尚未实现或执行切换 |

## 0x05 参考与版本

核对基线：`93ffe0df8872f72f55d96716491ee519e9d86634`（本地源码）。

- [日志页](https://github.com/TencentBlueKing/bk-monitor/blob/master/bkmonitor/webpack/src/apm/pages/application/app-configuration/storage-state/storage-state-log.tsx)
- [APM 日志数据源](https://github.com/TencentBlueKing/bk-monitor/blob/master/bkmonitor/apm/models/datasource.py)
- [日志平台更新入口](https://github.com/TencentBlueKing/bk-monitor/blob/master/bklog/apps/log_databus/handlers/collector/base.py)

| 状态 | 分支 | 里程碑 | PR |
| --- | --- | --- | --- |
| 🔄 | `<branch_name>` | 日志 ES 集群切换 | 待创建 |
