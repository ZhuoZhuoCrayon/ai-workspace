# 共享机器人的权限与部署

`0.3.0` 将管理配置与任务执行分开。企业微信模式必须使用独立的非 root 执行账号，控制进程负责鉴权、凭据、审计和会话存储。

## 0x01 身份与授权

| 角色 | 权限 | 配置入口 |
| --- | --- | --- |
| 未授权 | 查询自己的 `/whoami` | 管理员发送 `/allow <userid>` |
| 使用者 | 提问、管理自己的上下文、查看模型 | `wecom.allowedUsers` |
| 管理员 | 使用者权限、邀请与撤权、修改全局执行器和模型 | 本机配置 `wecom.adminUsers` |

管理员必须同时位于白名单。聊天管理指令只能增删普通使用者，管理员增删由本机运维完成。配置缺失、损坏或权限异常时，鉴权拒绝请求。

首次配对仍使用终端显示的限时配对码。首位正确完成配对的用户成为管理员，普通私聊不会触发注册。已有白名单升级时必须明确填写管理员，程序不按名单顺序推断身份。

`/whoami`、`/access`、`/allow` 和 `/deny` 由桥接程序处理，不调用模型。引用、附件及模型输出中的命令不会作为管理指令执行。撤权立即影响下一条消息，并取消该使用者正在运行的任务。

## 0x02 配置

示例中的用户 ID、系统账号 ID、目录和命令必须替换为本机实际值：

```json
{
  "channel": "wecom",
  "workspace": "/srv/ai-workspace",
  "stateDir": "/var/lib/agent-chat-controller/state",
  "healthPort": 8788,
  "execution": {
    "uid": 10001,
    "gid": 10001,
    "home": "/var/lib/bridge-agent"
  },
  "agents": {
    "codex": { "command": "/usr/local/bin/codex", "writable": true },
    "cursor": { "command": "/usr/local/bin/cursor-agent", "writable": true }
  },
  "wecom": {
    "allowedUsers": ["example-admin", "example-member"],
    "adminUsers": ["example-admin"]
  }
}
```

| 字段 | 约束 |
| --- | --- |
| `execution.uid`、`execution.gid` | 正整数，执行账号不属于 root |
| `execution.home` | 已存在的真实目录，由执行账号拥有，权限为 `0700` |
| `wecom.allowedUsers` | 不重复的实际发送者 ID，拒绝通配符 |
| `wecom.adminUsers` | 白名单的子集，已有使用者时必须明确配置 |

桥接按平台回调的发送者 ID 校验权限。昵称、引用中的身份声明和用户输入的管理员称呼不参与鉴权。

权限操作原子更新配置文件，其他配置字段保持不变。权限变更前必须写入审计意图，结果审计失败时回复提示管理员通过 `/access` 核对实际名单。

## 0x03 Linux 部署

### a. 目录与账号

1. 创建专用执行账号，禁止该账号登录为 root、使用 sudo 或管理桥接服务。
2. 将编译产物及依赖安装到执行账号不可改写的发布目录，例如 `/opt/agent-chat-bridge/0.3.0`。
3. 将配置和机器人 `.env` 存入 root 拥有的私有目录，例如 `/etc/agent-chat-bridge`，目录权限 `0700`、文件权限 `0600`。
4. 为执行账号准备独立 HOME，仅授予业务工作目录所需权限。
5. 使用执行账号完成 Codex、Cursor、Git 和业务工具的登录及配置，逐项验证可用性。

执行器只继承 `PATH`、语言、时区和终端信息，HOME 指向独立账号。机器人凭据、管理账号的环境变量和登录目录不会自动传给执行器。

不要把控制配置或服务发布目录放进执行账号可以移动、替换的目录。启动检查会验证配置、凭据、状态目录及其祖先目录的访问边界，并检查运行代码与 Node.js 程序不可由执行账号改写。

### b. 服务模板

Node.js、CLI 程序及其父目录必须允许执行账号遍历。服务控制进程需要 root 权限设置子进程 UID/GID，业务任务始终以配置中的执行账号运行。

```ini
[Unit]
Description=Agent Chat Bridge
After=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/agent-chat-bridge/0.3.0
ExecStart=/usr/local/bin/node dist/cli.js --config /etc/agent-chat-bridge/bridge.local.json
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
UMask=0077
KillMode=control-group
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

状态目录由控制进程管理。执行账号仅能遍历附件入口并读取分配的附件，不能读取会话状态、审计或锁文件。图片回传检查已打开文件的真实位置，拒绝目录替换和符号链接导致的越界读取。

### c. 升级与回滚

升级前备份运行配置和服务定义，并记录生效版本。执行以下验收后再让新版本接入真实机器人：

- 使用执行账号运行两种 CLI 的 `--version`，确认独立登录态和业务工具配置可用。
- 用本机权限测试确认执行账号无法读取或改写控制配置、凭据、状态和运行代码。
- 使用本地 WebSocket 回归验证拒绝、邀请、撤权、角色和会话边界。

等待运行任务结束后切换发布目录，启动新服务，并通过 `/healthz`、`/metrics` 和 `/whoami` 检查。旧配置缺少 `execution` 或管理员时，新版本拒绝启动，需要先完成配置迁移。

回滚时停止新服务，恢复备份配置和旧发布目录，再启动并验证连接。回滚到 `0.2.x` 会恢复旧版的权限边界，必须限制使用范围。

## 0x04 审计与验收

审计文件位于 `<stateDir>/audit/events.jsonl`，仅控制账号可读写。记录发送者 ID、哈希后的工作目录、消息与会话标识、权限操作、执行器和任务结果，不保存正文、密钥、工具输出或底层异常。

单文件达到 `10 MiB` 后轮转，保留 `3` 份备份。需要长期留存时，由运维采集到受控审计系统，不将原始日志提交到仓库。

```bash
npm run check
npm test
npm run build
```

普通环境运行确定性测试和官方 SDK 本地 WebSocket 集成。Linux root 测试环境还会运行真实降权用例，验证执行器及其 shell 子进程无法读写管理配置，并验证可写祖先目录会被启动检查拒绝。

角色隔离保护机器人管理面。共用执行账号仍共用业务目录与工具凭据，业务系统权限需要在对应 API 和凭据层控制。任务与凭据需要彼此隔离的使用者，应使用不同执行账号和独立实例。
