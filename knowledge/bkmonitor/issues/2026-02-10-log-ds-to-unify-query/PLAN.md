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

NAMESPACE="ieg-blueking-monitor-prod"
POD="bk-monitor-api-86459d8699-267wx"

LOCAL_PROJECT_ROOT="/remote-dev/Project/Github/bk/monitor/bk-monitor/bkmonitor"
kubectl cp ${LOCAL_PROJECT_ROOT}/constants/data_source.py -n ${NAMESPACE} ${POD}:/app/code/constants/data_source.py
kubectl cp ${LOCAL_PROJECT_ROOT}/bkmonitor/data_source/unify_query/query.py -n ${NAMESPACE} ${POD}:/app/code/bkmonitor/data_source/unify_query/query.py
kubectl cp ${LOCAL_PROJECT_ROOT}/bkmonitor/data_source/data_source/__init__.py -n ${NAMESPACE} ${POD}:/app/code/bkmonitor/data_source/data_source/__init__.py
kubectl cp ${LOCAL_PROJECT_ROOT}/bkmonitor/management/commands/reconcile_log_strategy.py -n ${NAMESPACE} ${POD}:/app/code/bkmonitor/management/commands/reconcile_log_strategy.py

kubectl exec -n ${NAMESPACE} ${POD} -it -- bash
```

### b. 统计日志策略

1）bkop 环境执行：

```bash
OUTPUT="/tmp/bkop_stats.csv"
python manage.py reconcile_log_strategy --mode stat --output ${OUTPUT}

```

2）ieod 环境执行：

```bash
OUTPUT="/tmp/ieod_stats.csv"
python manage.py reconcile_log_strategy --mode stat --output ${OUTPUT}
```

3）将生成的 CSV 从 Pod 中复制到本地：

```bash
kubectl cp ${NAMESPACE}/${POD}:${OUTPUT} ${OUTPUT}
```

### c. 执行对账

> ieod 环境，共 289 个业务、14416 个策略，按策略数量贪心分为 10 组。
> 对账时间 = `(当前 - 15 分钟, 当前)`，通过 `--start-time` / `--end-time` 传入秒级时间戳。

```bash
# 对账时间窗口：(now - 15min, now)
END_TIME=$(date +%s)
START_TIME=$((END_TIME - 900))
echo "对账时间范围: ${START_TIME} ~ ${END_TIME}"
```

**第 1 组**（1 个业务，5888 个策略）—— TGlog：

```bash
OUTPUT="/tmp/ieod_reconcile_$(date +%Y%m%d%H%M%S)_g01.csv"
python manage.py reconcile_log_strategy --mode reconcile --output ${OUTPUT} --start-time ${START_TIME} --end-time ${END_TIME} --biz-ids 622
```

**第 2 组**（1 个业务，5332 个策略）—— TAM前端监控：

```bash
OUTPUT="/tmp/ieod_reconcile_$(date +%Y%m%d%H%M%S)_g02.csv"
python manage.py reconcile_log_strategy --mode reconcile --output ${OUTPUT} --start-time ${START_TIME} --end-time ${END_TIME} --biz-ids 5000206
```

**第 3 组**（27 个业务，400 个策略）：

```bash
OUTPUT="/tmp/ieod_reconcile_$(date +%Y%m%d%H%M%S)_g03.csv"
python manage.py reconcile_log_strategy --mode reconcile --output ${OUTPUT} --start-time ${START_TIME} --end-time ${END_TIME} --biz-ids -4228598 5016744 100619 100842 820 5000558 -4220442 454 100386 5005578 -4232537 -4220657 730 1132 100566 100900 5016890 -4238074 -4223302 -4219888 173 393 1131 100564 101000 5000489 5016959
```

**第 4 组**（34 个业务，400 个策略）：

```bash
OUTPUT="/tmp/ieod_reconcile_$(date +%Y%m%d%H%M%S)_g04.csv"
python manage.py reconcile_log_strategy --mode reconcile --output ${OUTPUT} --start-time ${START_TIME} --end-time ${END_TIME} --biz-ids 100375 100644 591 100885 100978 100791 237 5000442 100167 -4220426 5016780 640 100391 -4228367 -4220326 590 100429 5016793 -4219841 766 1171 100626 100936 5016949 -4236880 -4220461 -4219884 239 481 1151 100729 101007 5000509 5016962
```

**第 5 组**（37 个业务，400 个策略）：

```bash
OUTPUT="/tmp/ieod_reconcile_$(date +%Y%m%d%H%M%S)_g05.csv"
python manage.py reconcile_log_strategy --mode reconcile --output ${OUTPUT} --start-time ${START_TIME} --end-time ${END_TIME} --biz-ids 100999 -4220075 100439 100674 -4244940 1068 100941 5016754 917 5016699 101010 151 5016836 706 100426 -4228266 61 943 100431 5017031 140 801 100133 100678 100970 -4255122 -4244504 -4235015 -4220437 -4219874 299 825 100147 100736 101014 5000580 5017052
```

**第 6 组**（37 个业务，400 个策略）：

```bash
OUTPUT="/tmp/ieod_reconcile_$(date +%Y%m%d%H%M%S)_g06.csv"
python manage.py reconcile_log_strategy --mode reconcile --output ${OUTPUT} --start-time ${START_TIME} --end-time ${END_TIME} --biz-ids 615 100771 639 100864 100867 100938 5002453 105 5016662 5016913 101080 348 123 100857 100442 -4228233 113 971 100599 -4254736 -4228111 228 815 100141 100723 101003 -4244496 -4234525 -4220352 104 302 834 100179 100764 101064 5016734 5017080
```

**第 7 组**（38 个业务，399 个策略）：

```bash
OUTPUT="/tmp/ieod_reconcile_$(date +%Y%m%d%H%M%S)_g07.csv"
python manage.py reconcile_log_strategy --mode reconcile --output ${OUTPUT} --start-time ${START_TIME} --end-time ${END_TIME} --biz-ids 100205 101002 -4220742 100956 100378 139 100603 494 5016879 100700 5016678 121 793 644 303 100951 100620 -4220802 120 1022 100974 -4247937 -4223350 236 918 100199 100801 101072 -4244112 -4228290 -4220313 106 307 901 100273 100768 101067 5016739
```

**第 8 组**（38 个业务，399 个策略）：

```bash
OUTPUT="/tmp/ieod_reconcile_$(date +%Y%m%d%H%M%S)_g08.csv"
python manage.py reconcile_log_strategy --mode reconcile --output ${OUTPUT} --start-time ${START_TIME} --end-time ${END_TIME} --biz-ids 5016750 132 5016779 -4220588 398 980 5016942 100749 970 100231 5016858 551 100965 835 852 5000565 100705 -4220778 137 100148 5000140 -4241539 -4222431 286 998 100371 100814 101073 -4243398 -4228285 -4220257 108 309 1051 100290 100793 5000157 5016852
```

**第 9 组**（38 个业务，399 个策略）：

```bash
OUTPUT="/tmp/ieod_reconcile_$(date +%Y%m%d%H%M%S)_g09.csv"
python manage.py reconcile_log_strategy --mode reconcile --output ${OUTPUT} --start-time ${START_TIME} --end-time ${END_TIME} --biz-ids 100394 5016987 902 100820 5011748 100915 848 111 100883 1057 100712 100380 5000555 100602 100475 -4228190 100149 5010264 397 100244 5000545 -4235129 -4220833 412 1010 100401 100869 5000448 -4243055 -4228184 -4220209 133 382 1113 100322 100840 5000173 5016882
```

**第 10 组**（38 个业务，399 个策略）：

```bash
OUTPUT="/tmp/ieod_reconcile_$(date +%Y%m%d%H%M%S)_g10.csv"
python manage.py reconcile_log_strategy --mode reconcile --output ${OUTPUT} --start-time ${START_TIME} --end-time ${END_TIME} --biz-ids 100627 101068 100993 555 596 5016796 100782 5006200 1092 100333 -4232440 100925 -4221037 -4228187 100780 344 100367 5016710 399 100325 5000592 -4234820 -4220762 480 1019 100409 100871 5000499 -4239493 -4228178 -4220143 150 392 1114 100361 100971 5000428 5016947
```

将生成的 CSV 从 Pod 中复制到本地（`kubectl cp` 不支持通配符，用 `tar` 批量传输）：

```bash
# 在 Pod 外执行：批量复制所有 ieod_reconcile_*.csv 到本地 /tmp/
kubectl exec -n ${NAMESPACE} ${POD} -- bash -c 'cd /tmp && tar cf - ieod_reconcile_*.csv' | tar xf - -C /tmp/
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

从对账 CSV 中提取不一致记录（`is_consistent=0`），生成 Excel 报告，并同步新增记录到企业微信智能表格。

### b. 工作目录

`csv/`——所有输入 CSV、输出 Excel、脚本均在此目录下。Agent 根据下方规格自行生成处理脚本，无需依赖已有脚本。

### c. 处理步骤

#### 步骤 1：读取 CSV 并过滤

- 扫描 `csv/` 目录下所有匹配 `*_reconcile_*.csv` 的文件。
- 文件命名格式：`{环境}_reconcile_{日期时间}.csv`（如 `bkop_reconcile_20260212153254.csv`）。
- 环境名从文件名提取（正则 `^(\w+?)_reconcile_`），如 `bkop`、`ieod`。
- CSV 列全部为字符串类型，具体字段见步骤 2 目标列定义中的数据来源。
- 过滤条件：`is_consistent == "0"`。

#### 步骤 2：列映射

将源字段映射为目标列，不直接保留的源字段（`query_config`、`data_type_label`、`is_consistent`）丢弃，`diff_reason` 翻译后映射为「原因」列。

**目标列定义**：

| 列名         | 数据来源                                                              |
|------------|-------------------------------------------------------------------|
| 环境         | `bkop` / `ieod`                                                   |
| 业务         | `{bk_biz_name}（#{bk_biz_id}）`                                     |
| 策略         | 超链接，显示文本 `{strategy_name}（#{strategy_id}）`，链接 `{strategy_url}`    |
| 处理人        | 空字符串                                                              |
| 优先级        | 固定 `P2`                                                           |
| 进度         | 固定 `发现`                                                           |
| 是否有数据      | `has_data`                                                        |
| 数据点数（UQ）   | `uq_count`                                                        |
| 数据点数（ES）   | `ds_count`                                                        |
| 原因         | `diff_reason` 翻译（见下方映射表），未匹配则保留原值                                 |
| 查询语句       | `query_string`                                                    |
| 聚合维度       | `agg_dimension`                                                   |
| 创建时间       | 新记录取脚本运行时间，格式 `YYYY-MM-DD HH:MM:SS`                               |

**diff_reason 翻译映射**：

| diff_reason           | 原因     |
|-----------------------|--------|
| EMPTY_DIMENSION_FIELD | 维度值为空  |
| DIFF_DATAPOINTS       | 数据值不一致 |
| DIFF_DIMENSION_FIELD  | 时序不一致  |

**唯一键**：`{环境}-{strategy_id}`，用于去重判断。

#### 步骤 3：写入 Excel（`csv/reconcile.xlsx`）

规则：
- 多环境、多时间点的对账数据写入同一个 Excel。
- 以唯一键（`{环境}-{策略 ID}`）去重：已存在的记录**不覆盖**（保留人为编辑的「处理人/优先级/进度/原因」等字段），仅追加新记录。
- 写入前自动备份：若 `reconcile.xlsx` 已存在，先复制为 `reconcile_backup_{YYYYMMDDHHMMSS}.xlsx`。
- 读取已有 Excel 时用 openpyxl（非 pandas），以保留超链接信息；从已有「策略」单元格还原唯一键时，用正则 `#(\d+)` 提取 strategy_id。
- 「策略」列写入时附带超链接（`cell.hyperlink = url`），并设置蓝色下划线字体。
- 表头样式：加粗、白字蓝底、居中。冻结首行。列宽自适应。

#### 步骤 4：检查结果（人工确认）

- 确认 Excel 格式正确，目标列无异常空数据。
- 与备份 Excel 对比，确认：新增记录合理、无重复、未覆盖人工编辑。

#### 步骤 5：同步新增记录到企业微信智能表格

**前置条件**：执行该步骤前，需在对话中给出「当前新增的记录数」、「新增记录最早的创建时间」，根据反馈（例如晚于 xxx 时间的记录才需要同步）来决定同步策略。

**接口信息**：
- 方法：`POST`
- URL：`https://qyapi.weixin.qq.com/cgi-bin/wedoc/smartsheet/webhook?key=<key>`
- `key`：从文件 `csv/.wx.key` 读取。

**字段 Schema**（field_id → 列名，写入请求体的 `schema` 字段）：

| field_id | 列名         |
|----------|------------|
| f0ckkJ   | 环境         |
| f0wYXZ   | 业务         |
| f1ULuB   | 策略         |
| f1z20U   | 处理人        |
| f287oU   | 优先级        |
| fBSUsV   | 进度         |
| fU4afj   | 是否有数据      |
| fVZePo   | 数据点数（UQ）   |
| fWCZhl   | 数据点数（ES）   |
| fdbzjB   | 原因         |
| fsXvKv   | 查询语句       |
| fzRDUF   | 聚合维度       |
| fyDRi3   | 创建时间       |

**字段值格式规则**：
- 普通文本字段：`[{"text": "内容"}]`
- 超链接字段（策略）：`[{"link": "URL", "text": "显示文本"}]`
- 处理人字段：`[{"user_id": ""}]`
- 创建时间字段：毫秒时间戳**字符串**（如 `"1739174400000"`）

**请求体示例**（一条记录）：

```json
{
    "schema": {
        "f0ckkJ": "环境",
        "f0wYXZ": "业务",
        "f1ULuB": "策略",
        "f1z20U": "处理人",
        "f287oU": "优先级",
        "fBSUsV": "进度",
        "fU4afj": "是否有数据",
        "fVZePo": "数据点数（UQ）",
        "fWCZhl": "数据点数（ES）",
        "fdbzjB": "原因",
        "fsXvKv": "查询语句",
        "fzRDUF": "聚合维度",
        "fyDRi3": "创建时间"
    },
    "add_records": [
        {
            "values": {
                "f0ckkJ": [{"text": "bkop"}],
                "f0wYXZ": [{"text": "{bk_biz_name}（#{bk_biz_id}）"}],
                "f1ULuB": [{"link": "{strategy_url}", "text": "{strategy_name}（#{strategy_id}）"}],
                "f1z20U": [{"user_id": ""}],
                "f287oU": [{"text": "P2"}],
                "fBSUsV": [{"text": "发现"}],
                "fU4afj": [{"text": "0"}],
                "fVZePo": [{"text": "2"}],
                "fWCZhl": [{"text": "0"}],
                "fdbzjB": [{"text": "时序不一致"}],
                "fsXvKv": [{"text": "(status:\"502\" OR status:\"503\")"}],
                "fzRDUF": [{"text": "[]"}],
                "fyDRi3": "1739174400000"
            }
        }
    ]
}
```

**同步策略**：
- 每次请求最多 **1000 条**记录，超过则分批发送。
- 每批间隔 **1 秒**。
- 请求失败打印错误信息，**不中断**后续批次，最终汇总成功/失败数。
- 需要网络访问权限（`full_network`）。

### e. 注意事项

- Agent 根据上述规格自行生成 Python 脚本，脚本放在 `csv/` 目录下。
- 步骤 3（写入 Excel）和步骤 5（同步企微）建议拆分为独立脚本或独立子命令，便于单独执行和重试。
- 先用少量数据验证脚本正确性，再批量执行。
- 查看第一行数据确认格式，使用脚本批量处理，以节省 Token。

## 0x04 状态

- [x] 需求已实现
- [ ] 对账验证中
- [ ] 对账结果分析

---
*制定日期：2026-02-10*
