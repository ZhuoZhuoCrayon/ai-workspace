# 配置与运行

在组件目录执行本文命令。日常配置保存在 `bridge.local.json`，修改后重启服务；首次创建使用 `npm run setup`，手工配置可从 [config.example.json](../config.example.json) 开始。

[返回 README](../README.md) · [配置字段](#0x02-配置字段) · [后台运行与探活](#0x03-后台运行与探活) · [状态与恢复](#0x04-状态与恢复)

## 0x01 常用操作

### a. 临时改用终端

已有企业微信配置时，可用终端检查 Agent 调用：

```bash
npm start -- --channel terminal
```

- *[1] `--channel` 只覆盖本次启动；先停止使用同一状态目录的服务，再运行此命令。*

### b. 从终端接入企业微信

停止服务，在 `bridge.local.json` 中将 `channel` 改为 `wecom`，准备凭据文件：

```bash
if [ ! -e .env ]; then
  install -m 600 .env.example .env
fi
```

编辑 `.env`，将占位值替换为机器人的 Bot ID 和 Bot Secret，然后前台启动：

```bash
npm start
```

白名单为空时，按 [README 首次对话流程](../README.md#c-启动并完成首次对话)完成绑定。

### c. 调整工作目录与写权限

编辑 `bridge.local.json` 中的对应字段，例如：

```json
{
  "workspace": "/Users/me/projects/my-app",
  "agents": {
    "codex": { "writable": true },
    "cursor": { "writable": false }
  }
}
```

- *[1] 这是待合并到已有配置的片段；工作目录必须存在，相对路径以配置文件目录为基准。*
- *[2] `writable` 默认 `false`；设为 `true` 后，Codex 使用 `workspace-write`，Cursor 使用 `--force`，按各自 CLI 的权限机制执行。*
- *[3] 工作目录参与会话隔离，修改后会进入另一组上下文。*

## 0x02 配置字段

所有字段均可省略，默认值如下。配置文件中的目录和含 `/` 的相对命令路径，以配置文件所在目录为基准。

### a. 服务与任务

| 字段 | 类型 | 默认值 | 约束 / 用途 |
| --- | --- | --- | --- |
| `channel` | string | `wecom` | `wecom` 或 `terminal` |
| `workspace` | string | `.` | Agent 固定工作目录，必须存在 |
| `stateDir` | string | `.state` | 会话、进程锁和入站附件目录 |
| `defaultAgent` | string | `codex` | `codex` 或 `cursor` |
| `maxConcurrent` | integer | `4` | 全局并发上限，范围 `1`～`32` |
| `requestsPerMinute` | integer | `10` | 每个平台账号下每个用户的分钟请求上限，范围 `1`～`100` |
| `idleTimeoutMs` | integer | `600000` | 连续无 Agent 输出的空闲时限，范围 `1000`～`86400000` 毫秒 |
| `hardTimeoutMs` | integer | `3600000` | 单任务绝对时限，范围 `1000`～`86400000` 毫秒 |
| `timeoutMs` | integer | 未设置 | 兼容旧配置的绝对时限；显式 `hardTimeoutMs` 优先 |
| `healthPort` | integer | `0` | `0` 关闭探活，端口范围 `1`～`65535` |
| `personaFile` | string | 未设置 | 本机表达风格文件，最大 `16,000` 字节，相对配置文件目录解析 |

- *[1] 同一会话始终串行，超出并发上限的请求立即拒绝；任务时限涵盖附件下载与 CLI 执行。*

默认连续 10 分钟没有 Agent 输出才触发空闲超时，任务总时长最多 60 分钟；两种时限均涵盖附件准备与 CLI 执行。CLI 标准输出（含工具事件、尚未组装完的大事件）和标准错误都会刷新空闲计时，企业微信进度推送和连接心跳不会续期。空闲超时、总时限和主动取消使用不同提示，停止时清理整个 CLI 进程组。

旧配置若显式设置 `timeoutMs: 600000`，仍保留 10 分钟绝对上限；迁移时删除该字段或显式设置 `hardTimeoutMs: 3600000`。企业微信单条流式消息窗口与任务时限独立，窗口结束不代表任务超时。

在已有 `bridge.local.json` 中修改以下字段，重启服务后生效。示例将空闲时限改为 15 分钟、总时限改为 90 分钟：

```json
{
  "idleTimeoutMs": 900000,
  "hardTimeoutMs": 5400000
}
```

`npm run setup` 创建的新配置显式写入默认时限。启用探活后，`/metrics` 的 `timeouts` 返回进程实际加载的两个值，可用于核对配置是否生效。

### b. 执行器与模型

`agents.codex` 和 `agents.cursor` 使用相同结构：

| 字段 | 类型 | 默认值 | 约束 / 用途 |
| --- | --- | --- | --- |
| `agents.<name>.command` | string | `codex` / `cursor-agent` | 可执行文件名或路径 |
| `agents.<name>.model` | string | 可选列表第一项 | 部署默认模型 ID |
| `agents.<name>.models` | string[] | 各自内置的 `4` 项 | `/model` 可选列表，最多 `30` 项且不重复，空数组使用内置列表 |
| `agents.<name>.writable` | boolean | `false` | Codex 默认 `read-only`，Cursor 默认 `ask` |
| `agents.codex.networkAccess` | boolean | `false` | 使用 `workspace-write` 时允许工具联网，例如调用 GitHub API |
| `agents.codex.fullAccess` | boolean | `false` | 显式启用 Full Access，跳过 Codex 沙箱和审批，优先于 `writable` 与 `networkAccess` |

内置模型如下，第一项为各自默认值：

| 序号 | Codex | Cursor |
| --- | --- | --- |
| `1` | GPT-6.1 Sol High（`gpt-6.1-sol`） | Grok 4.7 Extra High Fast（`grok-4.7-xhigh-fast`） |
| `2` | GPT-6 Astra High（`gpt-6-astra`） | Claude Opus 5.5 High Fast（`claude-opus-5-5-high-fast`） |
| `3` | GPT-6 Sol High（`gpt-6-sol`） | GPT-5.6 Sol High Fast（`gpt-5.6-sol-high-fast`） |
| `4` | GPT-5.6 Sol High（`gpt-5.6-sol`） | Composer 2.5 Fast（`composer-2.5-fast`） |

- *[1] Codex 通过 CLI 参数固定使用 `high` 推理强度和标准服务档位，覆盖本机 Fast 设置；Cursor 的强度和速度包含在模型 ID 中。*
- *[2] 模型实际可用性取决于 CLI 登录账号的权限。自定义 `models` 可覆盖内置列表，未指定 `model` 时使用自定义列表第一项。*

在聊天中发送 `/agent` 选择执行器，再发送 `/model` 选择对应模型。这两项选择对同一状态目录中的全部聊天生效，`/model default` 清除该执行器的覆盖值并恢复部署默认。各聊天仍按执行器保留各自上下文。

Codex 需要查询 GitHub 时，在已有配置的 `agents.codex` 中设置 `writable: true` 和 `networkAccess: true`，重启服务后生效。宿主机能访问 GitHub 不代表 Codex 沙箱已允许联网，匿名 API 限频也应与网络故障分别排查。

部署者明确选择 Full Access 时，设置 `agents.codex.fullAccess: true`。服务通过 `--dangerously-bypass-approvals-and-sandbox` 启动 Codex，仍按机器人白名单接收任务。

### c. 表达风格

在配置中设置 `personaFile` 指向自己的 Markdown 文件，编辑后重启服务。Codex 和 Cursor 共用该表达约定，每次请求都会附加，切换执行器不会丢失。

默认表达以结论为先，复杂问题再展开依据和下一步。CLI 的过程旁白、思考摘要和工具状态进入折叠区，正文保留最终答复，避免“我正在看、我已读取”挤占回答开头。

聊天答复按信息关系使用短段、列表、步骤或窄表。编写文档时遵循目标项目规范，聊天版式不覆盖用户要求的文档格式。

引用按证据对象选择团队网页、仓库文件、PR 或官方文档。仓库链接须对应实际所属仓库的已推送内容，嵌套私有仓库使用自己的 remote；未发布内容显示普通路径和状态。企业微信将残留的本地 Markdown 文本链接降级为可读路径，不猜远程地址。

### d. 企业微信

| 字段 | 类型 | 默认值 | 约束 / 用途 |
| --- | --- | --- | --- |
| `wecom.allowedUsers` | string[] | `[]` | 首次配对写入，也可手工维护明确的用户 ID，拒绝 `*` |
| `wecom.updateIntervalMs` | integer | `1500` | 流式更新合并间隔，范围 `1000`～`60000` 毫秒 |
| `wecom.streamWindowMs` | integer | `300000` | 进度消息窗口，范围 `5000`～`300000` 毫秒 |

凭据使用 `WECOM_BOT_ID` 和 `WECOM_BOT_SECRET`。显式环境变量优先于配置文件同目录的 `.env`，凭据不写入 JSON。

## 0x03 后台运行与探活

先完成首次绑定，再由进程管理器以同一系统账号运行。工作目录设为组件目录，启动命令为：

```bash
node dist/cli.js --config /absolute/path/to/bridge.local.json
```

- *[1] 部署或更新源码后先运行 `npm ci` 和 `npm run build`；进程环境中须包含 Node.js 和对应 CLI 的 PATH、登录态。*
- *[2] 同一 `stateDir` 只能运行一个实例；停止服务时发送 `SIGINT` 或 `SIGTERM`，服务会取消任务并释放锁。*

将 `healthPort` 设为 `8787` 并重启后检查：

```bash
curl --fail http://127.0.0.1:8787/healthz
curl --fail http://127.0.0.1:8787/metrics
```

| 接口 | 正常结果 | 判定范围 |
| --- | --- | --- |
| `/healthz` | HTTP `200`，`{"status":"ok"}` | 平台已连接且服务接收任务，企业微信还须存在绑定用户 |
| `/metrics` | HTTP `200`，含 `connected`、`accepting`、`running` 的 JSON | 连接、任务接收状态和运行任务数 |
| 聊天中的测试问题 | Agent 返回正文 | CLI 登录态、模型权限和实际调用 |

- *[1] 探活仅监听 `127.0.0.1`；`/healthz` 未就绪时返回 `503`，不验证模型登录态；`/metrics` 为 JSON 格式。*

## 0x04 状态与恢复

| 数据 | 重启后 | 保留范围 |
| --- | --- | --- |
| 执行器选择、模型偏好 | 恢复 | 同一状态目录内的全部聊天共用，不因闲置过期 |
| 当前上下文 | 恢复 | 按聊天和用户保留，不因闲置过期 |
| 归档会话 | 恢复 | 每种执行器最多 `10` 条，保留 `7` 天 |
| 上一条问题、消息去重和限频记录 | 清空 | 仅存于服务进程 |

会话上下文按工作目录、平台、机器人、聊天和用户隔离。执行器与模型选择保存在同一状态目录，对其中的全部聊天生效。备份配置、`.env` 和 `stateDir` 可保留本机设置与桥接会话记录，CLI 登录态由各自工具管理。

异常退出提示状态目录被占用时，查看 `stateDir` 下 `bridge.lock` 中的进程号，确认原服务停止后再删除该锁文件并重启。

向导生成的配置与凭据权限为 `0600`，状态目录为 `0700`。`.env`、`*.local.json` 和 `.state/` 均被 Git 忽略，CLI 子进程过滤 `WECOM_` 和 `BRIDGE_` 环境变量。

## 0x05 消息与引用

| 回调内容 | 处理 |
| --- | --- |
| 文本、语音转写、`mixed` 图文引用 | 提取正文和附件，保留引用标识 |
| 占位文字或空引用 | 明确标记原文缺失，保留本次提问与可见附件 |

Markdown 内容块引用与原文补取不在支持范围内。平台仅回传“该消息类型暂不能展示”时，用户需复制正文、转发可读文本或提供源链接。

## 0x06 CLI 事件

CLI 按 JSON 令牌流读取事件，桥接层只组装需要的字段。

| 数据或状态 | 处理 |
| --- | --- |
| 会话、进度与答复 | 交给协议解析器 |
| 工具参数与结果 | 按块消费，不累计完整事件 |
| 最终答复 | 保留 `100,000` 字符上限 |
| 无效 JSON、缺失终态、异常退出 | 任务判为失败 |
