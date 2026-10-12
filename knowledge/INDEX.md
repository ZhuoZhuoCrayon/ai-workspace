# 知识库索引

> 最后更新：2026-10-12

## 0x01 项目知识

| 项目 | 路径 | 数量 | 说明 |
|------|------|------|------|
| ai-workspace | [ai-workspace/](./ai-workspace/INDEX.md) | 5 篇 | AI 工作区 — 知识管理与多项目协作中枢 |
| bk-cli | [bk-cli/](./bk-cli/INDEX.md) | 0 篇 | 蓝鲸平台 API 命令行工具 |
| bkmonitor | [bkmonitor/](./bkmonitor/INDEX.md) | 49 篇 | 蓝鲸监控平台（bk-monitor/bkmonitor） |
| bkm-skills | [bkm-skills/](./bkm-skills/INDEX.md) | 6 篇 | BlueKing Monitor Skills |
| bk-product-designs | [bk-product-designs/](./bk-product-designs/INDEX.md) | 0 篇 | 蓝鲸监控产品设计协作仓库 |
| bkmonitor_mcp | [bkmonitor_mcp/](./bkmonitor_mcp/INDEX.md) | 1 篇 | 蓝鲸监控 MCP Server |
| bkmonitor-datalink | [bkmonitor-datalink/](./bkmonitor-datalink/INDEX.md) | 4 篇 | 蓝鲸监控数据链路 |
| bkmonitor-ecosystem | [bkmonitor-ecosystem/](./bkmonitor-ecosystem/INDEX.md) | 0 篇 | 蓝鲸监控生态 SDK 与接入 demo（外部版） |
| browser-sdk | [browser-sdk/](./browser-sdk/INDEX.md) | 0 篇 | Datadog Browser SDK |
| crypto-python-sdk | [crypto-python-sdk/](./crypto-python-sdk/INDEX.md) | 0 篇 | BlueKing 轻量级密码学工具包，统一加解密抽象层 |
| throttled-py | [throttled-py/](./throttled-py/INDEX.md) | 8 篇 | High-performance Python rate limiting library |
| 通用知识 | [_shared/](./_shared/INDEX.md) | 1 篇 | 跨项目通用知识 |

## 0x02 最近更新

- 2026-10-12：更新 [APM 服务数据状态下沉到后台服务发现](./bkmonitor/issues/2026-09-16-apm-service-data-status-heartbeat/README.md)（按里程碑 1 PR review 结论回写方案：心跳只记录观测到的服务并以行锁合并，调用链兜底轮跳过入口接口发现，性能分析服务按普通服务并入拓扑且保持串行发现，登记 PR 版本锚点）
- 2026-10-12：更新 [RUM 分层统一查询](./bkmonitor/issues/2026-08-07-rum-unified-query/README.md)（会话时间线支持按 `view_id` 查询单个 View）
- 2026-10-12：更新 [指标元信息存储与 SaaS/APM 自定义指标改造](./bkmonitor/issues/2026-09-15-custom-metric-metadata/README.md)（开发方案按开发者视角重写：实测按范围存放元信息的四种存法，选定定义加稀疏例外且例外引用去重取值；补齐有效配置解析器、服务范围对象、bmw 元信息消费、Histogram 复合面板与 APM V2 收敛命令的开发契约；在 MySQL `5.7` 上端到端对比四个完整方案，选定全建新表，已有表零 DDL）
- 2026-10-11：新增 [工作区跨主机一键初始化](./ai-workspace/issues/2026-10-11-workspace-portable-bootstrap/README.md)（注册表改为相对路径，私有数据迁入独立仓库，外部 skills 按锁文件固定版本，`make bootstrap` 只克隆缺失仓库并在本机生成 skills 链接）
- 2026-10-11：更新 [指标元信息存储与 SaaS/APM 自定义指标改造](./bkmonitor/issues/2026-09-15-custom-metric-metadata/README.md)（重建存储方案：指标项按指标名唯一并保留 BkBase 指标同步，上报范围与成员由 Collector 元信息维护，TimeSeriesScope 收窄为页面分组；按百万指标项完成展开、分表、窄成员表与三种元信息落点的满量压测和 MySQL 5.7/8.0 兼容实测，补充三阶段发布与 APM V2 收敛方案）
- 2026-10-10：更新 [RUM 分层统一查询](./bkmonitor/issues/2026-08-07-rum-unified-query/README.md)（设计会话时间线 Builder，节点详情复用 Span Builder；View 停留时长徽标改用 `field_unit` 声明单位）
- 2026-10-09：更新 [RUM 分层统一查询](./bkmonitor/issues/2026-08-07-rum-unified-query/README.md)（Vital 与 Error 详情去掉耗时徽标，View 关联查询按 View ID 定位）
