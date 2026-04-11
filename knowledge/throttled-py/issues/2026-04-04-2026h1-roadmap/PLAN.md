---
title: throttled-py 2026H1 演进 RoadMap
tags: [throttled-py, roadmap, planning, strategy, storage, integration]
issue: knowledge/throttled-py/issues/2026-04-04-2026h1-roadmap/README.md
description: 记录 throttled-py 2026H1 完整演进路线、关键接口、分月计划、测试策略与假设
created: 2026-04-04
updated: 2026-04-11
---

# throttled-py 2026H1 演进 RoadMap —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 调研

### a. 当前基线

- 能力现状：`throttled-py` 已具备 5 种算法、Sync/Async、Redis（单机、哨兵、集群）与 Memory、Otel Hook、完整 CI。
- 测试现状：本地基线为 `uv run pytest -q`，结果为 `641 passed, 51 skipped`。
- 生态现状（2026-04-04）：GitHub 为 `628 stars / 32 forks / 4 open issues / 1 open PR`，PyPI 最新版本为 `3.2.0`。

### b. 关键短板

- 场景短板：FastAPI、Flask、Django、DRF 缺少官方集成能力。
- 功能短板：多规则限流与可读容量配置尚未提供。
- 存储短板：缺少 ValKey、Memcached、MySQL 的官方后端支持。
- 稳定性短板：Redis 高可用缺少系统化混沌验证与报告沉淀。

### c. 已确认约束

- 范围约束：`throttled-rs` 在本周期不纳入执行范围。
- 方案约束：可读容量配置采用字符串 DSL。
- 优先级约束：优先主线为“场景集成 + 存储扩展”。

## 0x02 方案设计

### a. 关键接口与能力变更

- 配额接口：新增 `quota.parse("100/s; burst=200")` 与 `Throttled(quota="100/s; burst=200")`。
- 规则接口：新增 `rules=[Rule(...), Rule(...)]`，默认策略为 `ANY_LIMITED_DENY`。
- 集成接口：新增 `throttled.contrib.fastapi`、`throttled.contrib.flask`、`throttled.contrib.django`、`throttled.contrib.drf`。
- Key 提取：新增 `key_func(request) -> str`，内置 IP、User、API-Key 三类提取器。
- 存储策略：ValKey 复用 RedisStore。
- 存储策略：Memcached 先交付 Fixed/Sliding Window。
- 存储策略：MySQL 先交付 Fixed Window（事务 + UPSERT）。
- 文档策略：新增能力矩阵文档，覆盖算法 × 存储 × sync/async × wait-retry。

### b. 里程碑拆分

| 里程碑 | 时间 | 重点交付 | 验收要点 |
|------|------|------|------|
| M1 | 2026-04 | DSL、FastAPI、多规则 RFC 草案 | [1] DSL 兼容旧 API<br />[2] FastAPI 示例可运行<br />[3] 新增契约测试通过 |
| M2 | 2026-05 | 多规则执行引擎、Flask 集成 | [1] sync/async 语义一致<br />[2] Flask 覆盖用户与 IP 场景 |
| M3 | 2026-06 | ValKey、Redis HA 混沌一期 | [1] 故障注入无错误放量<br />[2] 恢复后一致<br />[3] 输出 v1 报告 |
| M4 | 2026-07 | Django 与 DRF 场景化 | [1] issue #111 类诉求可覆盖<br />[2] 示例项目可运行 |
| M5 | 2026-08 | Memcached 与 MySQL v1 | [1] 能力矩阵标注限制<br />[2] 契约与并发正确性测试通过 |
| M6 | 2026-09 | 稳定化与发布收口 | [1] 联调回归完成<br />[2] 发布清单与迁移文档对外可用 |

### c. GitHub issue 映射

- `quota DSL` 已通过 [PR #141](https://github.com/ZhuoZhuoCrayon/throttled-py/pull/141) 交付，不再补建新的 GitHub issue。
- `Release stabilization and release pack` 暂不创建 issue。
- 进入发布收口阶段后，再决定是否单独跟踪。

| Issue | 需求 | 进度 | 更新时间 |
|------|------|------|------|
| [Add official FastAPI integration #149](https://github.com/ZhuoZhuoCrayon/throttled-py/issues/149) | 提供官方 FastAPI 集成，支持路由级限流、`key_func` 和最小可运行示例。 | 新建 | 2026-04-11 |
| [RFC: multi-rule limiting API and semantics #150](https://github.com/ZhuoZhuoCrayon/throttled-py/issues/150) | 定义 `rules=[...]` API、`ANY_LIMITED_DENY` 默认策略、短路语义和 sync/async 一致性。 | 新建 | 2026-04-11 |
| [Implement multi-rule execution engine #151](https://github.com/ZhuoZhuoCrayon/throttled-py/issues/151) | 实现多规则执行引擎，并补齐 `peek`、短路和 sync/async 一致性测试。 | 新建 | 2026-04-11 |
| [Add official Flask integration #152](https://github.com/ZhuoZhuoCrayon/throttled-py/issues/152) | 提供官方 Flask 集成，覆盖用户/IP 限流场景和最小可运行示例。 | 新建 | 2026-04-11 |
| [Add ValKey backend support #153](https://github.com/ZhuoZhuoCrayon/throttled-py/issues/153) | 复用 RedisStore 语义提供官方 ValKey 支持，并补齐兼容性验证和 CI 覆盖。 | 新建 | 2026-04-11 |
| [Add Redis HA chaos validation v1 #154](https://github.com/ZhuoZhuoCrayon/throttled-py/issues/154) | 建立 Redis 高可用混沌验证一期，覆盖切主、失联、恢复一致性并输出第一版报告。 | 新建 | 2026-04-11 |
| [Help: Integrate with Django #111](https://github.com/ZhuoZhuoCrayon/throttled-py/issues/111) | 提供 Django 官方集成能力，支持 per-view、per-IP、per-user 限流并减少重复配置。 | 复用现有 issue | 2026-04-11 |
| [Add official DRF integration #155](https://github.com/ZhuoZhuoCrayon/throttled-py/issues/155) | 提供官方 DRF 集成，覆盖 `APIView`、`ViewSet` 用法和可运行示例。 | 新建 | 2026-04-11 |
| [Add Memcached backend v1 #156](https://github.com/ZhuoZhuoCrayon/throttled-py/issues/156) | 提供 Memcached v1 后端，先支持 Fixed Window 和 Sliding Window，并明确能力边界。 | 新建 | 2026-04-11 |
| [Add MySQL backend v1 #157](https://github.com/ZhuoZhuoCrayon/throttled-py/issues/157) | 提供 MySQL v1 后端，先支持 Fixed Window，并补齐事务与并发正确性测试。 | 新建 | 2026-04-11 |

### d. 版本发布边界

- `v3.3.x`：DSL、多规则、FastAPI、Flask、ValKey。
- `v3.4.x`：Django、DRF、Memcached/MySQL（v1）、Redis HA 报告。

## 0x03 实施步骤

1. 在 M1 落地 DSL 与 FastAPI，并补齐契约测试基线与示例文档。
2. 在 M2 落地多规则核心与 Flask，补齐 `peek` 与短路语义验证。
3. 在 M3 落地 ValKey 与 Redis HA 混沌一期，形成第一版验证报告。
4. 在 M4 落地 Django 与 DRF 场景接入，完成 issue #111 类诉求闭环。
5. 在 M5 落地 Memcached 与 MySQL v1，补充能力边界与推荐阈值文档。
6. 在 M6 完成跨模块联调、性能回归、发布清单与对外文档收口。

## 0x04 实施进展（表格）

| 时间 | 对应设计片段 | 结论调整概要 | 改动 / 验证 |
|------|----------------|----------------|-------------|
| 2026-04-11 | `0x02.b`、`0x02.c` | [1] 将里程碑拆分进一步细化为可追踪的 GitHub issue 映射。<br />[2] `quota DSL` 已完成，不再补建 GitHub issue。<br />[3] 发布收口阶段暂不提前创建 GitHub issue。 | [1] 新建 GitHub issues `#149` 至 `#157`。<br />[2] Django 方向复用现有 issue [#111](https://github.com/ZhuoZhuoCrayon/throttled-py/issues/111)。<br />[3] 在 `PLAN` 中新增 issue 映射表并同步 `updated` 日期。 |

## 0x05 参考

### a. 测试与质量门禁

- 契约测试：所有 Store 必须通过统一 Store Contract（`exists`、`ttl`、`set`、`get`、`hset`、`hgetall`、`atomic`）。
- 一致性测试：同一规则在 Memory、Redis、ValKey、Memcached、MySQL 的限流判定一致。
- 混沌测试：覆盖 Redis 哨兵切主、集群节点失联、网络延迟和丢包、客户端重连风暴。
- 集成测试：提供 FastAPI、Flask、Django、DRF 四套最小应用端到端验证。
- 性能测试：单机与并发对比 `v3.2.0` 基线，确保核心路径无明显回退。

### b. 执行假设

- `throttled-rs` 不纳入 2026H1 范围。
- Memcached 与 MySQL 先以 v1 能力交付，不承诺首版覆盖全部 5 种算法。
- 路线优先级保持“接入门槛低、主路径高性能、可靠性可验证”。

---
*制定日期：2026-04-04*
