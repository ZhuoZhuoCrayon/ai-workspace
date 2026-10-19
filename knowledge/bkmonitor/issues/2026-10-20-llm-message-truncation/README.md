---
title: LLM 消息截断容错展示
tags: [apm, llm, json, truncation, frontend]
description: 避免截断消息被误判为空，保留可解析内容并提示数据不完整
created: 2026-10-20
updated: 2026-10-20
---

# LLM 消息截断容错展示

## 0x01 背景

### a. Why

大语言模型（LLM）观测中的消息字段可能因长度限制被截断，形成不完整 JSON。
页面把解析失败的消息视为空数组，导致仍有有效内容的对话历史无法展示。
已核验样本的输出可正常展示，尚未复现输入截断导致输出同时空白。

### b. 目标

- 保留截断消息中可解析的内容，明确提示数据不完整。
- 输入、输出分别降级，解析失败时提供原文查看。

## 0x02 实现路线

### a. 建议的方案

由前端消息解析入口统一处理完整、截断和异常数据，优先评估现成的部分 JSON 解析库，详见 [问题样例与方案对比](./PLAN.md)。

### b. 约束

恢复范围限于留存数据，已丢失的尾部内容无法补回。
文档和测试采用合成样例，不保存真实业务标识、内网地址、消息正文或鉴权信息。

## 0x03 参考

- [partial-json](https://github.com/promplate/partial-json-parser-js)
- [jsonrepair](https://github.com/josdejong/jsonrepair)
