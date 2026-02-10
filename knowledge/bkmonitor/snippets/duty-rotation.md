---
title: 轮值配置
tags: [duty, rotation, user-group]
description: 告警组轮值配置的 API 请求示例
language: python
created: 2026-02-09
updated: 2026-02-09
---

# 轮值配置

## 0x01 关键信息

### a. 适用场景

创建和配置告警组的轮值规则。

## 0x02 代码片段

### a. 创建告警组请求示例

API 路径：`/rest/v2/user_groups/`

```json
{
    "name": "sand测试2",
    "desc": "",
    "need_duty": true,
    "duty_rules": [2],
    "duty_notice": {},
    "alert_notice": [
        {
            "time_range": "00:00:00--23:59:00",
            "notify_config": [
                {"level": 3, "notice_ways": [{"name": "rtx"}]},
                {"level": 2, "notice_ways": [{"name": "rtx"}]},
                {"level": 1, "notice_ways": [{"name": "rtx"}]}
            ]
        }
    ],
    "action_notice": [
        {
            "time_range": "00:00:00--23:59:00",
            "notify_config": [
                {"level": 3, "notice_ways": [{"name": "rtx"}], "phase": 3},
                {"level": 2, "notice_ways": [{"name": "rtx"}], "phase": 2},
                {"level": 1, "notice_ways": [{"name": "rtx"}], "phase": 1}
            ]
        }
    ],
    "mention_list": [{"id": "all", "type": "group"}],
    "channels": ["user", "wxwork-bot"],
    "bk_biz_id": 2
}
```
