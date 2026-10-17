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
| `timeoutMs` | integer | `600000` | 单任务时限，范围 `1000`～`86400000` 毫秒 |
| `healthPort` | integer | `0` | `0` 关闭探活，端口范围 `1`～`65535` |

- *[1] 同一会话始终串行，超出并发上限的请求立即拒绝；任务时限涵盖附件下载与 CLI 执行。*

### b. 执行器与模型

`agents.codex` 和 `agents.cursor` 使用相同结构：

| 字段 | 类型 | 默认值 | 约束 / 用途 |
| --- | --- | --- | --- |
| `agents.<name>.command` | string | `codex` / `cursor-agent` | 可执行文件名或路径 |
| `agents.<name>.model` | string | CLI 账号默认 | 部署默认模型 ID |
| `agents.<name>.models` | string[] | `[]` | `/model` 可选列表，最多 `30` 项且不重复 |
| `agents.<name>.writable` | boolean | `false` | Codex 默认 `read-only`，Cursor 默认 `ask` |

要启用聊天中的模型切换，将账号可用的模型 ID 填入对应的 `models`。`/model default` 清除当前会话的覆盖值，恢复 `model` 或 CLI 账号默认。

### c. 企业微信

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
| 执行器选择、当前上下文、模型偏好 | 恢复 | 当前会话不因闲置过期 |
| 归档会话 | 恢复 | 每种执行器最多 `10` 条，保留 `7` 天 |
| 上一条问题、消息去重和限频记录 | 清空 | 仅存于服务进程 |

会话按工作目录、平台、机器人、聊天和用户隔离。备份配置、`.env` 和 `stateDir` 可保留本机设置与桥接会话记录，CLI 登录态由各自工具管理。

异常退出提示状态目录被占用时，查看 `stateDir` 下 `bridge.lock` 中的进程号，确认原服务停止后再删除该锁文件并重启。

向导生成的配置与凭据权限为 `0600`，状态目录为 `0700`。`.env`、`*.local.json` 和 `.state/` 均被 Git 忽略，CLI 子进程过滤 `WECOM_` 和 `BRIDGE_` 环境变量。
