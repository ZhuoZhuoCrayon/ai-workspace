---
title: 通用聊天 Agent 桥接组件
tags: [agent, bridge, codex, cursor]
description: 在聊天平台中调用本地 Codex 和 Cursor，并按会话切换执行器
created: 2026-10-17
updated: 2026-10-17
---

# 通用聊天 Agent 桥接组件

## 0x01 背景

### a. Why

聊天机器人与单一 Agent 绑定，使平台接入、会话管理和执行器替换相互牵连。需要一个可独立运行的组件，将聊天平台协议与本地 Agent CLI 分开。

### b. 目标

- 提供 Codex 和 Cursor 执行器，通过 `/agent` 按会话切换并恢复各自上下文。
- 保留企业微信多轮消息、附件、进度与限频能力，通过 `npm start` 向导和私聊配对完成初次接通。
- 使用通用名称和平台接口，通过 PreCI 后放入公开工作区，无法剥离的内容留在私有域。

## 0x02 实现路线

### a. 建议的方案

采用 `agent-chat-bridge` 组件、平台适配器、会话控制器和 CLI 执行器三层结构。安装向导生成本机配置，企业微信通过短期私聊配对码确认访问者。实现、自动化测试和组件快照 PreCI 已通过，本地交付证据及真实账号联调边界见 [实施方案](./PLAN.md)。

### b. 约束

- 仅提供 Codex 和 Cursor 两种 Agent，不提供 Claude 执行器或配置兼容层。
- 微信和飞书通过平台接口扩展，交付文档明确实际实现的平台。
- 原项目源码核对、PreCI 检测和文档验收是交付门禁。
- 架构、代码、文档和协议调研分工自查，修复后复查并更新方案证据。

## 0x03 参考

- [实施方案](./PLAN.md)
- [Codex 非交互模式](https://learn.chatgpt.com/docs/non-interactive-mode)
- [Cursor CLI 输出协议](https://cursor.com/docs/cli/reference/output-format)
- [企业微信官方 Node.js SDK](https://github.com/WecomTeam/aibot-node-sdk)
