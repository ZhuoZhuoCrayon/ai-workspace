# Agent Chat Bridge

把企业微信或本地终端接到 Codex 和 Cursor，在同一会话里用 `/agent` 切换执行器。平台消息协议、会话控制和 CLI 运行器分别维护，新增聊天平台时复用同一套会话和执行协议。

## 0x01 快速开始

### a. 安装并启动

运行环境为 macOS 或 Linux，Node.js 最低版本为 `22.12`，`.nvmrc` 使用 `22.15.1`。要使用的 Codex 或 Cursor CLI 需由运行服务的同一系统账号安装并登录。

```bash
cd apps/agent-chat-bridge
nvm use
npm ci
npm start
```

`npm start` 自动构建并启动；首次在交互终端运行时会打开向导。向导询问平台、工作目录、默认执行器和是否允许修改文件，默认使用企业微信、当前目录、Codex 和只读权限。选择企业微信时再填写 Bot ID 和隐藏输入的 Bot Secret。

向导生成本机配置 `bridge.local.json`，企业微信凭据写入 `.env`，两者权限均为 `0600`。已有配置和凭据不会被覆盖；也可先运行 `npm run setup` 单独初始化。

选择 `terminal` 可直接在终端对话，选择 `wecom` 可接入企业微信长连接机器人。工作目录可以是普通目录或 Git 项目，启动后固定使用该目录。

CLI 安装与登录方法见 [Codex CLI](https://learn.chatgpt.com/docs/codex/cli) 和 [Cursor CLI](https://cursor.com/docs/cli/overview)，常用登录命令为：

```bash
codex login
cursor-agent login
```

### b. 首次绑定企业微信

白名单为空时，前台启动会显示一条包含 `8` 位十六进制随机码、`10` 分钟有效的配对指令。在企业微信中私聊机器人，发送终端显示的指令：

```text
/pair <配对码>
```

绑定成功后，用户 ID 自动写入本机白名单，无需预先查询。该用户可在私聊和机器人所在群聊中提问；群聊不能发起首次配对，未绑定用户的普通消息不启动 Agent。

完成首次绑定后可按普通服务方式启动，重启不会重复配对。配对码过期时重启前台服务生成新码，白名单为空时要求交互终端。

## 0x02 会话命令

| 命令 | 行为 |
| --- | --- |
| `/agent` | 显示当前执行器和会话状态 |
| `/agent codex`、`/agent cursor` | 切换当前会话的执行器 |
| `/status` | 显示任务状态和上下文是否可恢复 |
| `/reset`、`/new` | 归档当前执行器的上下文并开启新会话 |
| `/sessions` | 列出当前执行器的归档会话 |
| `/resume <序号>` | 恢复列表中的历史会话 |
| `/model` | 显示当前模型和部署配置中的可选列表 |
| `/model <模型 ID>`、`/model default` | 设置当前执行器的模型或恢复部署默认 |
| `/rerun` | 重跑服务进程内记录的上一条问题 |
| `/cancel`、`/stop` | 取消当前任务 |
| `/help` | 查看命令帮助 |

Codex 和 Cursor 分别保存会话 ID、归档和模型选择，切回执行器时恢复各自上下文。会话同时按工作目录、平台、机器人、聊天和用户隔离，群聊中的不同成员也拥有独立上下文。

任务运行期间，切换执行器、恢复历史、重置和修改模型会被拒绝。忙碌会话的新任务和超出全局并发上限的任务会立即收到提示，用户可取消任务后重新发送。

## 0x03 消息与附件

企业微信支持文本、语音转写、图片、文件、图文混排和引用内容。每条消息最多 `5` 个附件，图片上限为 `10 MB`，文件上限为 `20 MB`。

附件在用户授权、去重、限频和任务准入通过后下载，下载与 Agent 执行共用任务时限，可通过 `/cancel` 中止。入站附件以随机文件名落盘，原文件名只用于显示。Codex 图片通过 `--image` 参数传入，其他附件和 Cursor 图片以本地路径提供给 Agent。

Agent 在终稿中使用 `![说明](本地路径)` 可发送工作目录内的 PNG 或 JPEG 图片。每条回复最多 `3` 张，单张上限为 `10 MB`，真实路径越出工作目录的符号链接会被拒绝。

长任务超过平台流式窗口后，服务会封口进度消息，完成时主动推送结果。超长结果按 UTF-8 字节分段，代码围栏在分段时保持闭合。

## 0x04 进阶配置

日常使用只需向导生成的文件。自定义模型、并发或服务部署时，可编辑 `bridge.local.json`，修改配置后重启服务。[config.example.json](./config.example.json) 提供手工配置起点；企业微信凭据通过环境变量或配置目录中的 `.env` 提供。

### a. 指定运行入口

```bash
npm start -- --config bridge.local.json --channel terminal
npm start -- --config bridge.local.json --channel wecom
```

配置文件中的相对路径均以配置文件目录为基准。`--channel` 覆盖配置中的 `channel`，不修改本机文件。

### b. 任务与执行器

```json
{
  "channel": "wecom",
  "workspace": "../..",
  "stateDir": ".state",
  "defaultAgent": "codex",
  "agents": {
    "codex": { "command": "codex", "writable": false, "models": [] },
    "cursor": { "command": "cursor-agent", "writable": false, "models": [] }
  },
  "wecom": { "allowedUsers": ["your-user-id"] }
}
```

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `workspace` | 配置文件所在目录 | 固定的 Agent 工作目录，参与会话隔离 |
| `stateDir` | `.state` | 会话、锁和入站附件的存放目录 |
| `defaultAgent` | `codex` | 新会话使用 `codex` 或 `cursor` |
| `agents.<name>.command` | `codex` 或 `cursor-agent` | 可执行文件名或路径 |
| `agents.<name>.model` | CLI 账号默认 | 部署默认模型 ID |
| `agents.<name>.models` | `[]` | `/model` 允许选择的模型 ID 列表 |
| `agents.<name>.writable` | `false` | Codex 使用 `read-only`，Cursor 使用 `ask` 模式 |
| `maxConcurrent` | `4` | 全局任务并发上限，同一会话始终串行 |
| `requestsPerMinute` | `10` | 每个平台账号下、每个用户的分钟请求上限 |
| `timeoutMs` | `600000` | 单任务时限，超时终止 CLI 进程组 |

启用 `writable` 后，Codex 使用 `workspace-write`，Cursor 使用 `--force`。部署者应按工作目录和用户白名单授予执行能力，两种 CLI 的权限机制各自生效。

### c. 平台与探活

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `wecom.allowedUsers` | `[]` | 首次通过配对写入，也可手工维护明确的用户 ID 列表 |
| `wecom.updateIntervalMs` | `1500` | 合并流式进度更新的间隔 |
| `wecom.streamWindowMs` | `300000` | 超过窗口后封口进度消息，完成时主动推送结果 |
| `healthPort` | `0` | 非零时在本机环回地址提供 `/healthz` 和 `/metrics` |

企业微信发送队列串行调度并限制发送速度。凭据也可由 `WECOM_BOT_ID` 和 `WECOM_BOT_SECRET` 环境变量提供，显式环境变量优先于配置目录中的 `.env`。

## 0x05 运行状态与恢复

`stateDir` 的目录权限为 `0700`，会话文件权限为 `0600`。会话保存使用临时文件和原子替换，服务重启后恢复执行器选择、上下文 ID、历史和模型偏好。

当前会话不因闲置自动丢失，每种执行器最多保留 `10` 条归档，归档保留期为 `7` 天。上一条问题、消息去重记录和限频窗口仅保存在内存，服务重启后清空。

同一状态目录只允许一个服务进程运行。异常退出遗留锁文件时，先检查 `bridge.lock` 中的进程号，确认对应服务停止后再移除锁文件。

`.env`、`*.local.json`、`.state/` 和构建依赖不进入版本库。CLI 子进程会过滤 `WECOM_` 和 `BRIDGE_` 环境变量，Agent 自身的认证仍使用 CLI 登录态或其官方环境变量。

## 0x06 开发与扩展

```bash
npm run check
npm test
npm run build
```

| 扩展位置 | 契约 |
| --- | --- |
| 聊天平台 | 转换为 `IncomingMessage`，调用 `Bridge.handle()`；耗时附件处理通过可选 `prepare` 回调在准入后执行 |
| 平台回复 | 实现 `Reply.update()` 和 `Reply.finish()`，负责平台限频、分段和交付失败 |
| Agent | 实现 `Agent.run()`，返回会话、正文和完成事件，遵守取消信号 |
| 会话存储 | `SessionStore` 管理上下文与执行器选择，平台适配器不持有执行器会话 |

现有平台入口是企业微信和终端。微信和飞书接入可沿用上述契约，需要各自实现认证、消息接收和回复适配。

## 0x07 验证与来源

类型检查、构建及全量自动化测试通过。企业微信集成测试使用官方 SDK 和本地 WebSocket 服务；真实 Codex CLI 在普通非 Git 目录完成两轮调用，成功捕获和恢复同一会话，并在第二轮记住首轮验证词。

组件的 `40` 个 Git 候选交付文件快照通过 PreCI，扫描排除被忽略的依赖、构建产物和运行状态。Cursor 真实账号和企业微信真实机器人仍需在部署环境联调；完整证据与扫描范围见 [实施方案](../../knowledge/ai-workspace/issues/2026-10-17-agent-chat-bridge/PLAN.md)。

本组件采用 [MIT License](./LICENSE)，复用的文本分段器保留原作者版权声明。CLI 协议依据 [Codex 非交互模式](https://learn.chatgpt.com/docs/non-interactive-mode)、[Cursor 输出协议](https://cursor.com/docs/cli/reference/output-format) 和 [企业微信官方 SDK](https://github.com/WecomTeam/aibot-node-sdk)。
