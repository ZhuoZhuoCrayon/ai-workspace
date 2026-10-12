# 指标存储验证工程

本工程按 `1,000,000` 个指标项的平台基线生成数据，比较上报关系的展开、分表与窄成员表，元信息的扩列、一对一表与定义表，以及按范围不同的元信息的四种存法，并在 MySQL `5.7`、`8.0` 上验证 DDL、执行计划与写入 SQL。结论见 [REPORT](../REPORT.md)。

## 0x01 运行

依赖本机 MySQL `9.2.0`、uv 与 Docker，在本目录执行：

```bash
make env
make m1 m2
make explode
make meta-layout
make compat
```

| 套件 | 命令 | 数据库 | 数据目录峰值 | 本地输出 |
| --- | --- | --- | --- | --- |
| 运行环境 | `make env` | 本机 `9.2.0` | — | `results/environment.txt` |
| 元信息落点，活跃规模 | `make m1` | 本机 `9.2.0` | `8.2 GiB` | `results/m1_catalog.txt` |
| 元信息落点，上界规模 | `make m2` | 本机 `9.2.0` | `12.8 GiB` | `results/m2_catalog.txt` |
| 展开与分表 | `make explode` | 本机 `9.2.0` | 约 `17 GiB` | `results/m1_explode.txt` |
| 按范围不同的元信息 | `make meta-layout` | 本机 `9.2.0` | `4.3 GiB` | `results/meta_layout.txt` |
| 版本兼容 | `make compat` | Docker `5.7`、`8.0` | 约 `3 GiB` | `results/compat_57.txt`、`results/compat_80.txt`、`results/compat_diff.txt` |
| 冒烟 | `make catalog-smoke` | 本机 `9.2.0` | `2.9 GiB` | `results/catalog_smoke.txt` |

- *[1] [run.sh](./run.sh) 在 `$TMPDIR/cm-metric-bench` 初始化独立 mysqld（端口 `33306`，缓冲池 `8 GiB`，`innodb_flush_log_at_trx_commit=1`，关闭 binlog），由 `CM_BENCH_SCRIPT` 选择 `bench.py` 或 `catalog.py`。*
- *[2] [explode.py](./explode.py) 与 [meta_layout.py](./meta_layout.py) 各自启动 mysqld，端口为 `33309` 与 `33310`。*
- *[3] [compat.sh](./compat/compat.sh) 依次启动 `5.7`、`8.0` 容器，结束即删除容器与数据卷，Docker Hub 不可达时用 `IMAGE_57`、`IMAGE_80` 指定镜像源。*
- *[4] 数据目录用 `make clean`、`make explode-clean` 与 `make meta-layout-clean` 删除。*

早期的方案矩阵与 `__scope` 表示仍可复跑：

```bash
make s1 s2 layout
make scope scope-stress
```

## 0x02 数据画像

活跃规模（`make m1`）与上界规模（`make m2`）都是 `1,000,000` 个指标项，按数据源分为五档，最大档是单数据源的设计上界：

| 档 | 活跃规模数据源 | 上界规模数据源 | 每源指标 | 活跃规模每源服务 | 上界规模每源服务 | 上界规模每源成员 |
| --- | --- | --- | --- | --- | --- | --- |
| 最大 | `5` | `5` | `20,000` | `667` | `667` | `1,000,000` |
| 大型 | `600` | `1,550` | `221` | `28` | `126` | `19,966` |
| 中型 | `2,000` | `2,000` | `145` | `6` | `12` | `1,409` |
| 小型 | `3,000` | `3,000` | `83` | `4` | `8` | `436` |
| 微型 | `2,058` | `167` | `111` | `2` | `2` | `111` |

- *[1] 大型、中型、小型、微型的指标数与服务数取自 bkte 业务 `-4228598` 的四个 APM 应用，原始查询记录在 [cloud_scale.txt](./cloud_scale.txt)。*
- *[2] 上界规模把大型档的服务数放大到登记服务数 `126`，成员总数达到 `40,091,444`。*
- *[3] `30%` 的指标为 Histogram 拆分，`25%` 的 `scope_name` 为 `custom`，`5%` 的旧指标没有元信息，成员中 `1%` 带例外、`0.1%` 带按范围覆盖、`2%` 已过期。*
- *[4] 按范围不同的元信息另用 `1,500,000` 个成员的数据集，含最大档 `20,000` 个指标 × `50` 个范围，例外比例分 `1%`、`10%`、`50%` 三档。*

## 0x03 表名前缀

脚本与输出文件用前缀区分方案，前缀与 REPORT 中的方案名对应如下：

| 前缀 | REPORT 方案 | 对应表 |
| --- | --- | --- |
| R1 | 展开方案，服务并入 `field_scope` | `a_metric` |
| R2 | 分表方案，展开表按 `group_id % 16` 分表 | `a_metric_00` 至 `a_metric_15` |
| R4 | 窄成员表，上报范围、标签倒排与成员三张表 | `report_scope`、`report_scope_label`、`report_member` |
| X1 | 扩列，`TimeSeriesMetric` 加列 | `x1_timeseriesmetric` |
| X2 | 一对一表，按 `field_id` 关联 | `x2_metric_meta` |
| X3 | 定义表，按 `(group_id, field_name)` 关联 | `x3_metric_meta` |
| K1 至 K5 | `__scope` 的五种表示 | `k1_string` 至 `k5_column` |

- *[1] 早期方案见 [REPORT：早期方案矩阵](../REPORT.md#a-早期方案矩阵)，其中「服务并入 `field_scope`」即 R1，采用的「定义、范围与成员各一张表」即 R4 加 X3。*

## 0x04 口径

- *[1] 读取计时为 Unix socket 上的服务端执行与 pymysql 读取结果集的时间，不做类型转换。*
- *[2] 轻量用例预热 `30` 次后计 `300` 次，整组与全量扫描按用例减少次数，见各输出文件表头。*
- *[3] 体积取 `ANALYZE TABLE` 后 `information_schema` 的数据加索引，另列 `.ibd` 文件大小。*
- *[4] 缓冲池能容纳热数据，结果代表内存命中时的执行成本。*
- *[5] 版本兼容在 Docker Desktop 卷上运行，DDL 绝对耗时偏大，重点看是否重建、元数据锁行为与执行计划是否一致。*
