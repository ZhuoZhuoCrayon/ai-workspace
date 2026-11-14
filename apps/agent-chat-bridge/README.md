# Agent Chat Bridge

在企业微信中使用本机 Codex 和 Cursor。执行器和模型对所有聊天生效，上下文按聊天保留。也可直接在终端对话。

[快速开始](#0x01-快速开始) · [会话命令](#0x02-会话命令) · [消息与附件](#0x03-消息与附件) · [常见问题](#0x04-常见问题) · [配置与运行](./docs/configuration.md) · [开发指南](./docs/development.md)

## 0x01 快速开始

需要 macOS 或 Linux、Node.js `22.12` 及以上，以及一个已登录的 Codex 或 Cursor CLI。企业微信接入还需长连接机器人的 Bot ID 和 Bot Secret，凭据获取方式见[企业微信官方 SDK](https://github.com/WecomTeam/aibot-node-sdk)。

### a. 准备一个执行器

选择本次要使用的执行器，使用运行桥接服务的同一系统账号完成安装和登录。

**Codex**：按 [Codex CLI 文档](https://learn.chatgpt.com/docs/codex/cli)安装后运行：

```bash
codex --version
codex login
```

**Cursor**：按 [Cursor CLI 文档](https://cursor.com/docs/cli/overview)安装后运行：

```bash
cursor-agent --version
cursor-agent login
```

### b. 获取并初始化

```bash
git clone https://github.com/ZhuoZhuoCrayon/ai-workspace.git
cd ai-workspace/apps/agent-chat-bridge
npm ci
npm run setup
```

- *[1] 已有仓库时，从组件目录执行 `npm ci` 即可继续初始化。使用 nvm 时，可先运行 `nvm install`，按 `.nvmrc` 安装并切换到 Node.js `22.15.1`。*

在向导中填写：

| 提示 | 填写内容 |
| --- | --- |
| 聊天平台 | 接入企业微信选 `wecom`，本地试用选 `terminal` |
| Agent 工作目录 | 填写要让 Agent 处理的**已有项目目录**，例如 `/Users/me/projects/my-app` |
| 默认执行器 | 填写上一步准备的 `codex` 或 `cursor` |
| 允许修改工作目录 | 首次使用保留 `N`，以只读模式运行 |
| Bot ID / Bot Secret | 仅 `wecom` 需要，Secret 输入时不回显 |

- *[1] 向导生成 `bridge.local.json` 和企业微信所需的 `.env`，已有文件不会被覆盖；修改已有配置见[配置与运行](./docs/configuration.md)。*

### c. 启动并完成首次对话

```bash
npm start
```

**企业微信**：在终端找到 `/pair` 指令，私聊机器人并原样发送。收到“绑定成功，可以直接发送问题。”后继续下一步。

```text
/pair <终端显示的配对码>
```

- *[1] 配对码有效期为 `10` 分钟，过期后重启服务获取新码；首次绑定须在前台交互终端完成，群聊不接受配对。*

**终端**：看到“终端已就绪”后，直接在当前终端输入消息。

在所选入口依次发送以下两条消息，每次等待回复：

```text
/status
请只回复 READY。
```

第一条应显示当前执行器和“空闲”状态，第二条应收到 `READY`。完成第二条才说明 Agent 调用成功，`/status` 只验证桥接服务响应。

## 0x02 会话命令

### a. 执行任务

| 命令 | 用途 |
| --- | --- |
| `/agent` | 展示执行器清单和企微快捷选项 |
| `/agent 1`、`/agent 2` | 切换到 Codex 或 Cursor，也可直接填写名称 |
| `/status` | 查看当前执行器、模型、任务状态和上下文 |
| `/model` | 展示当前执行器的模型清单和企微快捷选项 |
| `/model <序号或模型 ID>`、`/model default` | 选择模型，或恢复该执行器的默认模型 |
| `/cancel`、`/stop` | 取消当前任务 |
| `/rerun` | 重跑当前执行器的上一条问题 |

- *[1] 同一会话同时执行 `1` 个任务，运行期间拒绝切换执行器、修改模型和调整上下文。*
- *[2] 其他会话可以修改全局选择，已开始的任务保持开始时的执行器和模型。*
- *[3] `/rerun` 依赖进程内记录，服务重启后需重新发送问题。*

每个执行器内置 `4` 个[常用模型](./docs/configuration.md#b-执行器与模型)。Codex 默认 GPT-6.1 Sol High，使用标准速度；Cursor 默认 Grok 4.7 Extra High Fast。

### b. 管理上下文

| 命令 | 用途 |
| --- | --- |
| `/reset`、`/new` | 归档当前执行器的上下文，开始新会话 |
| `/sessions` | 查看当前执行器的归档会话 |
| `/resume <序号>` | 恢复归档列表中的会话 |
| `/help` | 查看全部命令 |

Codex 和 Cursor 各自保存上下文与归档。执行器和模型选择对所有聊天生效，切回执行器时继续该执行器自己的对话。群聊中的不同用户拥有独立上下文，已绑定用户也可在机器人所在群聊中提问。

## 0x03 消息与附件

| 企业微信输入 / 输出 | 支持范围 |
| --- | --- |
| 输入消息 | 文本、语音转写、图文混排和引用内容 |
| 输入附件 | 每条消息最多 `5` 个，图片单张 `10 MB`，文件单个 `20 MB` |
| 输出图片 | 工作目录内的 PNG 或 JPEG，每条回复最多 `3` 张，单张 `10 MB` |
| 长文本结果 | 自动分段，保留代码围栏 |
| 长任务结果 | 超过流式窗口后结束进度消息，任务完成时另行推送结果 |
| 思考与进度 | 单独展示 CLI 提供的思考摘要和工具状态，完成后折叠，正文独立显示 |

- *[1] 让 Agent 在终稿中用 `![说明](本地路径)` 引用图片即可回传，真实路径必须位于工作目录内。*
- *[2] 语音使用平台提供的转写文本；附件下载和执行共用任务时限，均可用 `/cancel` 取消。*

## 0x04 常见问题

| 现象 | 处理方式 |
| --- | --- |
| 启动提示 CLI 不可用 | 用运行服务的账号执行对应的 `--version` 命令，确认安装与 PATH，或设置 `agents.<name>.command` |
| `/status` 正常，提问却提示执行器退出异常 | 在本机重新运行对应的 `login` 命令，检查模型和权限，再发送测试问题 |
| 企业微信普通消息没有触发任务 | 确认服务仍在运行，先在私聊中完成 `/pair`，再发送 `/status` |
| 提示首次配对需要前台终端 | 在交互终端运行 `npm start` 并完成绑定，再转为后台运行 |
| 再次运行向导没有重新提问 | 已有配置会直接复用，编辑 `bridge.local.json` 后重启服务 |
| 提示会话忙碌或服务繁忙 | 等待当前任务结束，或先 `/cancel` 再重新发送，服务不排队 |

更改工作目录、开放写权限、接入企业微信、后台启动和状态恢复，见[配置与运行](./docs/configuration.md)。

## 0x05 开发与验证

扩展平台或执行器，见[开发指南](./docs/development.md)。企业微信和终端是已实现的入口，微信和飞书需要另写适配器。

自动化测试覆盖企业微信官方 SDK 的本地 WebSocket 集成，真实 Codex 和 Cursor CLI 均已验证任务调用与上下文恢复。接入自己的机器人后，按[首次对话流程](#c-启动并完成首次对话)验收聊天收发。

架构与初始验收见[实施方案](../../knowledge/ai-workspace/issues/2026-10-17-agent-chat-bridge/PLAN.md)，版本变化见[变更记录](./CHANGELOG.md)。

本组件采用 [MIT License](./LICENSE)，复用的文本分段器保留原作者版权声明。
