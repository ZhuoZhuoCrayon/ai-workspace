# 终版表结构复测工程

本工程按 PLAN 终版表结构复测方案 E「取值去重」，并在同一 MySQL `5.7` 容器、同一库内与基线 D「元信息建表」对照。终版只有 `TimeSeriesReportValue` 与 `TimeSeriesReportScope` 两张上报表，没有标签表。复测范围包括写入、过期、两个读取方向与整组预取。DDL 与关键执行计划另在 MySQL `8.0` 上复核。

## 0x01 运行

依赖 Docker 与 uv。在本目录执行：

```bash
./run.sh        # 5.7 全量压测后接 8.0 复核，结束或失败都删除容器与数据卷
./run.sh 57     # 只跑 5.7
./run.sh 80     # 只跑 8.0
```

| 步骤 | 脚本 | 数据库 | 本地输出 |
| --- | --- | --- | --- |
| Django DDL 生成 | [django_ddl.py](./django_ddl.py) | `5.7`、`8.0` | `results/django_ddl_57.sql`、`results/django_ddl_80.sql` |
| 冒烟 | `bench.py smoke57`、`bench.py smoke80` | `5.7`、`8.0` | `results/smoke57.txt`、`results/smoke80.txt` |
| S1、S2、S3x 对照 | `bench.py s1`、`s2`、`s3x` | `5.7` | `results/s1.txt`、`results/s2.txt`、`results/s3x.txt` |
| 冷启动事务粒度对照 | `bench.py s1tx` | `5.7` | `results/s1tx.txt` |
| 服务视图耗时拆解 | [svcview_profile.py](./svcview_profile.py) | `5.7` | `results/svcview_profile_<库>.txt` |
| 溢出页验证 | [overflow.py](./overflow.py) | `5.7` | `results/overflow_<warm\|cold>_<库>.txt` |
| 执行计划 | [explain.py](./explain.py) | [a] `5.7` 上用 S1、S2、S3x、S3 的数据<br />[b] `8.0` 上自造 `10` 个数据源 | `results/explain_<库>_<版本>.txt` |
| S3 全平台上界 | [s3_size.py](./s3_size.py) | `5.7` | `results/s3.txt` |
| `TimeSeriesScope` 迁移 | [scope_ddl.py](./scope_ddl.py) | `5.7`、`8.0` | `results/scope_ddl_57.txt`、`results/scope_ddl_80.txt` |

- *[1] 容器参数：[run.sh](./run.sh) 启动 `pk6-b1-mysql`（`biarms/mysql:5.7`，`5.7.30` arm64，端口 `33341`）与 `pk6-b1-mysql80`（`mysql:8.0`，端口 `33342`），两者都用 `4 GiB` 缓冲池、`innodb_flush_log_at_trx_commit=1`、关闭 binlog、DYNAMIC 行格式，并关闭缓冲池的启动加载与退出转储。*
- *[2] 单独运行：脚本从 `MYSQL_HOST`、`MYSQL_PORT` 读取连接，默认 `127.0.0.1:33341`，例如 `uv run --with 'pymysql==1.1.1' bench.py s1`。*
- *[3] 溢出页冷读：`overflow.py cold` 必须在 mysqld 刚重启后运行，由 `run.sh` 负责重启容器。*

## 0x02 数据画像

| 场景 | scope | 指标名 | 取值 | 上报关系 | 说明 |
| --- | --- | --- | --- | --- | --- |
| S1 | `1,000` | `2,000` | `2,000` | `2,000,000` | 全部服务上报同一批元信息一致的指标 |
| S2 | `1,001` | `50,773` | `51,728` | `1,861,522` | [a] `5` 种 SDK 画像，每种 `1～3` 个元信息版本<br />[b] 稀疏 `182,248` 条，已过期 `37,191` 条<br />[c] 另有 `1` 个 DEFAULT scope |
| S3x | `667` | `20,000` | `20,200` | `1,000,500` | 最大档单数据源，每服务 `1,500` 个指标，`1%` 指标多一种取值 |
| S3 | `246,969` | 约 `1,000,000` | 约 `1,010,000` | 约 `40,000,000` | 全平台上界，只装终版表 |

- *[1] 生成器与 pk5 压测相同：S1、S2 沿用同一随机种子，取值去重结果与 pk5 一致。S2 的 DEFAULT scope 上报画像 `0` 的最新版本，放在随机抽样之后追加。*
- *[2] 终版协议：每个取值都带 `original_type`（拆分前类型）与 `metric_type`（本条序列类型）。Histogram 与 Summary 的 `_bucket`、`_sum`、`_count` 子项 `metric_type` 为 `counter`。*
- *[3] S3 的 D 体积不装载：引用 validation 上界规模实测 `7,849 MiB`，分布见 [validation README](../README.md) 0x02。*

## 0x03 实现要点

| 对象 | 终版（脚本前缀 `f_`） | 基线 D（脚本前缀 `d_`） |
| --- | --- | --- |
| 表 | [a] `f_value` 即 `TimeSeriesReportValue`<br />[b] `f_scope` 即 `TimeSeriesReportScope`<br />[c] `f_override` 即 `TimeSeriesMetricOverride` | `d_meta`、`d_value`、`d_scope`、`d_scope_label`、`d_member` |
| 写入 | 按数据源聚批 `30,000` 条，进程内缓存 scope 的 `version` 与取值 ID，批末逐 scope 事务提交，`scope_count` 用一条 `CASE id` 语句增减 | 与 pk5 相同，先查存在性再插入或刷新，成员 `24 h`、定义 `30 min` 刷新一次 |
| 过期 | `(group_id, last_seen)` 找过期 scope，回减 `scope_count` 后删除，再删 `scope_count = 0` 的取值 | 按 scope 分段走成员唯一键前缀，服务端过滤 `last_seen` |
| 服务视图 | 全组 `id, labels, last_seen` → 内存按 `service_name` 过滤 → 命中行的 `report_value_ids` → 按主键批量取取值 → 取覆盖 | 标签表 → `d_scope.labels` → 成员连定义 → 例外取值 |
| 整组预取 | 全组取值，DEFAULT scope 引用的取值优先，否则取 `scope_count` 最大者，并列取 ID 小者 | 全组定义 |
| 按指标取 scope | 按 `field_name` 取取值 ID → 解码全组 `report_value_ids` → 命中行的 `labels` | 定义 → 成员 `(group_id, meta_id)` 索引 → scope |

- *[1] 终版 DDL 与 Django 生成一致：`django_ddl.py` 用 Django `4.2.27` 的 schema editor 生成 SQL，`design_f.py` 只把建索引语句并入建表语句。*
- *[2] D 的 `5.7` 退化已修正：行构造 `IN` 按 `200` 组分段，过期扫描不再用 `(a > ? OR (a = ? AND b > ?))` 翻页，服务视图不回连标签表。*
- *[3] D 的类型计数口径：D 的 `metric_type` 存旧协议 `__type`（即拆分前类型），按成员期望类型与定义上的类型比较。*

## 0x04 口径

- *[1] 计时为 TCP 上的端到端时间：包含 pymysql 类型转换与 Python 解码，本次只有一个压测任务，绝对耗时可用。*
- *[2] 写库行数取 `Innodb_rows_inserted`、`Innodb_rows_updated` 与 `Innodb_rows_deleted` 的全局增量，并与语句返回的影响行数核对。输出中的 `statements` 含前后两条 `SHOW GLOBAL STATUS`。*
- *[3] 读取用例预热 `30` 次后计 `300` 次。整组预取为 `5/30`，D 过期扫描为 `1/5`。*
- *[4] 体积取 `ANALYZE TABLE` 后 `information_schema` 的数据加索引，另列 `.ibd` 文件大小。*
- *[5] 缓冲池能容纳全部数据：除 `overflow.py cold` 外，结果代表内存命中时的成本。*
- *[6] 迁移耗时在 Docker 卷上测得：重点看算法、是否重建表与元数据锁行为。*
