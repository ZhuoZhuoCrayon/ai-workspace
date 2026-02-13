---
title: 日志数据源切换 unify-query —— 实施方案
tags: [log, unify-query, data-source]
issue: ./README.md
description: 日志数据源切换到 unify-query 的实施方案
created: 2026-02-10
updated: 2026-02-10
---

# 日志数据源切换 unify-query —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 变更文件

### a. 主实现 (d802715f)

- `bkmonitor/data_source/data_source/__init__.py` - 日志数据源切换核心逻辑
- `bkmonitor/data_source/unify_query/query.py` - unify-query 适配
- `bkmonitor/utils/event_related_info.py` - 事件关联信息处理
- `constants/data_source.py` - 数据源常量

### b. 对账脚本 (0806795b)

- `bkmonitor/data_source/data_source/__init__.py` - 补充导出
- `management/commands/reconcile_log_strategy.py` - 查询对账命令

## 0x02 查询对账

### a. 同步代码到 Pod

```bash
NAMESPACE="blueking"
POD="bk-monitor-web-68cc644ccd-6vwbh"
LOCAL_PROJECT_ROOT="/remote-dev/Project/Github/bk/monitor/bk-monitor/bkmonitor"
kubectl cp ${LOCAL_PROJECT_ROOT}/constants/data_source.py -n ${NAMESPACE} ${POD}:/app/code/constants/data_source.py
kubectl cp ${LOCAL_PROJECT_ROOT}/bkmonitor/data_source/unify_query/query.py -n ${NAMESPACE} ${POD}:/app/code/bkmonitor/data_source/unify_query/query.py
kubectl cp ${LOCAL_PROJECT_ROOT}/bkmonitor/data_source/data_source/__init__.py -n ${NAMESPACE} ${POD}:/app/code/bkmonitor/data_source/data_source/__init__.py
kubectl cp ${LOCAL_PROJECT_ROOT}/bkmonitor/management/commands/reconcile_log_strategy.py -n ${NAMESPACE} ${POD}:/app/code/bkmonitor/management/commands/reconcile_log_strategy.py

kubectl exec -n ${NAMESPACE} ${POD} -it -- bash
```

### b. 统计日志策略

bkop 环境执行：

```bash
OUTPUT="/tmp/bkop_stats.csv"
python manage.py reconcile_log_strategy --mode stat --output ${OUTPUT}

kubectl cp ${NAMESPACE}/${POD}:${OUTPUT} ${OUTPUT}
```

ieod 环境执行：

```bash
python manage.py reconcile_log_strategy --mode stat --output ieod_stats.csv
```

### c. 执行对账

bkop 环境执行：

```bash
OUTPUT="/tmp/bkop_reconcile_$(date +%Y%m%d%H%M%S).csv"
python manage.py reconcile_log_strategy --mode reconcile --output ${OUTPUT} --biz-ids 2 7 9 10 37 54 -50

kubectl cp ${NAMESPACE}/${POD}:${OUTPUT} ${OUTPUT}
```

### d. 指定策略对账（调试用）

直接指定策略 ID 进行对账，同时输出 `ds_records` 和 `uq_records` 到 stdout：

```bash
# 指定单个策略
python manage.py reconcile_log_strategy --mode reconcile --strategy-ids 12345

# 指定多个策略
python manage.py reconcile_log_strategy --mode reconcile --strategy-ids 12345 12346 12347
```

> 注：指定 `--strategy-ids` 时，`--biz-ids` 参数将被忽略。

## 0x03 对账结果分析

### a. 目标

从对账 CSV 中提取不一致记录（`is_consistent=0`），生成便于分析的 Excel 报告。

### b. 处理步骤

1）**读取所有的 CSV**：`csv/{环境（bkop/ieod）}_reconcile_{日期}.csv`
2）**过滤数据**：提取 `is_consistent=0` 的记录
3）**列处理**：
   - 移除 `query_config`、`diff_reason`、`data_type_label`、`is_consistent` 列
   - 目标列定义：

     | 中文列名     | 数据来源                                                           |
     |----------|----------------------------------------------------------------|
     | 环境       | `bkop` / `ieod`                                                |
     | 业务       | `{bk_biz_name}（#{bk_biz_id}）`                                  |
     | 策略       | 超链接，显示文本 `{strategy_name}（#{strategy_id}）`，链接 `{strategy_url}` |
     | 处理人      | 放空即可。                                                          |
     | 优先级      | `P0`、`P1`、`P2`，默认 `P0`。                                        |
     | 进度       | `发现`、`跟进`、`解决`，默认为 `发现`                                        |
     | 是否有数据    | `has_data`                                                     |
     | 数据点数（UQ） | `uq_count`                                                     |
     | 数据点数（ES） | `ds_count`                                                     |
     | 原因       | `diff_reason` 翻译（见下表）                                          |
     | 查询语句     | `query_string`                                                 |
     | 聚合维度     | `agg_dimension`                                                |

4）**diff_reason 翻译**：

   | diff_reason           | 原因     |
   |-----------------------|--------|
   | EMPTY_DIMENSION_FIELD | 维度值为空  |
   | DIFF_DATAPOINTS       | 数据值不一致 |
   | DIFF_DIMENSION_FIELD  | 时序不一致  |

5）**目标 Excel**：`csv/reconcile.xlsx`。
- 存在不同环境，多个时间点的对账数据，需写入同一个目标 Excel。
- 更新规则：以 `${环境}-${策略 ID}` 为唯一键，存在则不重复写入，不存在则创建「不一致」记录。
- Excel 会被人为更新（例如更新「原因/进度」等），因此不应删除已存在的记录，保持每次更新都有备份的习惯。

6）**检查结果**：
- 确认生成的 Excel 格式正确，目标列不存在不符合预期的空数据。
- 与备份的 Excel 进行对比，确认新增记录合理，未出现重复记录，没有覆盖人为编辑的内容。

7）**注意**：查看第一行数据确认格式，使用脚本进行处理，以节省 Token。

## 0x04 状态

- [x] 需求已实现
- [ ] 对账验证中
- [ ] 对账结果分析

---
*制定日期：2026-02-10*
