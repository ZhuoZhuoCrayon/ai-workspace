---
name: work-schedule
description: 需求排期录入工具——将工作事项同步到企业微信智能表格。当用户提到"加入排期"、"录入排期"、"更新排期表"、"需求排期"、"把 xxx 加到排期"等意图时触发。也适用于用户提供新周期 schema/key 要求配置新文档的场景。
---

# 需求排期录入 Skill

## 0x01 背景与目标

通过企业微信智能表格 Webhook 将工作事项录入排期表。核心目标：

- 对话里出现“加入排期”时可快速落表
- 一个 `key` 对应一个文档，一个文档覆盖半年
- 固定脚本执行，减少人工拼装请求体错误

## 0x02 配置规范

配置文件路径：`.cursor/skills/work-schedule/config/schedules.yaml`

```yaml
active: "2026H1"
schedules:
  "2026H1":
    key: "webhook-key"
    months_start: 1
    schema:
      frvG4J: "项目"
      fzSueb: "需求"
      # ... field_id -> 列名
```

字段含义：

- `active`：当前默认周期
- `key`：Webhook key（仅保存在 `schedules.yaml`）
- `months_start`：`1` 或 `7`，用于 H1/H2 月份映射
- `schema`：`field_id -> 列名`，不同文档 field_id 不同

新增周期时必须执行：

1. 解析用户提供的 `schema + key`
2. 打印拟新增配置摘要（`period/key/months_start/schema`）并确认
3. 用户确认后再写入 `.cursor/skills/work-schedule/config/schedules.yaml`
4. 按用户要求决定是否切换 `active`

## 0x03 字段 Schema（扩展版）

> 以下为 2026H1 示例。实际以 `.cursor/skills/work-schedule/config/schedules.yaml` 为准。

| field_id | 列名 | 类型 | 默认值 | 字段说明 |
|----------|------|------|--------|---------|
| frvG4J | 项目 | multi_select | 自动猜测 | APM / APM / 日常支持 / 观测平台 / 文档建设 / 技术学习 |
| fzSueb | 需求 | text | 必填 | 需求名称或简述 |
| fc5FyT | 需求类型 | multi_select | 研发 | 研发 / 纯跟进 / 设计 / 原型 / 修复 |
| f53B4X | 优先级 | multi_select | P2 | `P0 / P1 / P2 / done` |
| fiWfNd | 进度 | multi_select | 未启动 | 未启动 / 评审中 / 暂时挂起 / 待产品确认方案 / 方案就绪 / 开发中 / 灰度中 / 已上线发布 / 跟进中 |
| fl1uff | 文档/链接 | link | [] | 文档链接，支持空 |
| f0B8fw | 事项类型 | multi_select | 规划 | 规划 / 新增 |
| ffio2F | 备注 | text | "" | 补充说明 |
| fYhKHf | 1 月 | month_tags | 自动计算 | 例如 `["P2-排期"]` |
| f6MQpU | 2 月 | month_tags | 自动计算 | 例如 `["P2-排期"]` |
| fYDW9O | 3 月 | month_tags | 自动计算 | 例如 `["P2-排期"]` |
| fNocoV | 4 月 | month_tags | 自动计算 | 例如 `["P2-排期"]` |
| fB1bqi | 5 月 | month_tags | 自动计算 | 例如 `["P2-排期"]` |
| fxHuQY | 6 月 | month_tags | 自动计算 | 例如 `["P2-排期"]` |
| fjgnwh | 图片 | image | [] | 图片附件，默认空 |

值格式规则：

| 类型 | 格式 | 示例 |
|------|------|------|
| multi_select | `[{"text": "值"}]` | `[{"text": "APM"}]` |
| text | 原始字符串 | `"需求描述"` |
| link | `[{"link":"url","text":"显示文本"}]` 或 `[]` | `[{"link":"https://...","text":"设计文档"}]` |
| month_tags | `[{"text":"Px-排期"}]` | `[{"text":"P2-排期"}]` |
| image | `[]` | `[]` |

## 0x04 月份自动计算规则

这里的 `P1/P2/P3` 是“旬别标签”，不是“优先级”。

- Day 1-10 -> `P1-*`
- Day 11-20 -> `P2-*`
- Day 21-31 -> `P3-*`

月份标签支持：

- `P1-排期 / P2-排期 / P3-排期`
- `P1-完成 / P2-完成 / P3-完成`
- `P1-延后 / P2-延后 / P3-延后`

若未提供 `月份`，脚本按当前日期自动填充一个月份标签，并按以下规则选择后缀：

- 事项完成（如 `优先级=done` 或 `进度=已上线发布`）-> `Px-完成`
- 事项延后（如 `进度=暂时挂起`）-> `Px-延后`
- 其他情况 -> `Px-排期`

## 0x05 项目归属规则

缺省 `项目` 时，脚本按关键词猜测：

- APM / Trace / 链路 / Span -> `APM`
- 日常支持 / 答疑 / 排障 / oncall -> `APM / 日常支持`
- 文档 / wiki / 规范 -> `观测平台 / 文档建设`
- 学习 / 调研 / 分享 -> `技术学习`

## 0x06 执行流程

1. 用户提出“加入排期”
2. 构造记录 JSON（可省略 `项目` 和 `月份`）
3. 先在对话中打印记录，用户确认
4. 执行脚本写入
5. 返回接口结果

执行命令：

```bash
python .cursor/skills/work-schedule/scripts/add_record.py \
  --config .cursor/skills/work-schedule/config/schedules.yaml \
  --record /tmp/schedule_record.json
```

说明：

- 需要 `full_network` 权限
- 脚本默认会二次确认请求体
- 如果上游已确认，可加 `--yes` 跳过二次确认

## 0x07 输入与命令示例

记录 JSON（列名语义）：

```json
{
  "项目": "APM",
  "需求": "告警日志支持 Doris",
  "需求类型": "研发",
  "优先级": "P1",
  "进度": "未启动",
  "事项类型": "规划",
  "备注": "",
  "文档/链接": [],
  "月份": {
    "3": ["P2-排期"]
  }
}
```

预览模式（仅打印请求体）：

```bash
python .cursor/skills/work-schedule/scripts/add_record.py \
  --config .cursor/skills/work-schedule/config/schedules.yaml \
  --record /tmp/schedule_record.json \
  --dry-run
```
