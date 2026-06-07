---
name: code-review
description: 执行代码审查、PR review、复查、处理未解决 review threads、发 review 评论、request changes 或 approve 前必须使用。适用于检查 GitHub PR diff、本地变更、相关源码、测试覆盖、项目规范和既有评论，并输出对话草稿，或在明确授权后发布 inline / conversation review 评论。
---

# Code Review

## 0x01 定位

`code-review` 负责审查 PR 或代码变更的正确性、兼容性、可维护性与发布风险。

默认只在对话中输出 review 草稿，不发布到 PR。

GitHub 写操作必须得到用户明确授权，包括评论、approve、request changes 和 dismiss review。

唯一例外：用户触发 review 后，针对已确认修复的既有未解决 review thread，可以自动 resolve。

## 0x02 权限门禁

### a. GitHub 写操作

用户明确说以下意图时，才执行对应 GitHub 写操作：

| 用户意图 | 动作 |
| --- | --- |
| `评论到 PR` / `发 review` / `发到 PR` | 发布对应 inline / conversation 评论。 |
| `Request Changes` / `请求修改` | 存在 P0 或阻塞合入问题时执行 request changes。 |
| `Approve` / `通过` | 先输出复查结论，再执行 approve，默认 approve body 为 `LGTM`。 |

授权模糊时必须先确认，不得猜测执行。

### b. Assignees

PR review 场景开始前必须补齐 assignees，未完成前不得继续 review 或执行 GitHub 写操作。

1. `gh api user --jq .login` 获取当前登录用户。
2. `gh pr view <pr> --json author --jq .author.login` 获取 PR 作者。
3. 去重后执行 `gh pr edit <pr> --add-assignee <login>`。
4. 执行 `gh pr view <pr> --json assignees --jq '.assignees[].login'` 校验。

失败时停止并告知用户，等待用户决策后再继续。

## 0x03 上下文收集

开始审查前，必须同时建立项目规范、变更内容和历史评论三类上下文。

| 上下文 | 要求 |
| --- | --- |
| 项目定位 | 目标项目已知时，先按工作区项目定位规则进入项目 `local_path`。 |
| 项目规范 | 优先读取目标仓库 `AGENTS.md`，再按项目类型读取 `pyproject.toml`、`package.json`、`go.mod`、lint / typecheck 配置等。 |
| 变更内容 | 查看 PR diff、本地 diff、相关源码、测试和配置变更。 |
| 历史评论 | 查看已有评论、未解决 review threads，以及用户要求复查的旧问题。 |

不要只看 diff 片段就下结论。

## 0x04 审查重心

优先关注会影响合入安全的问题，再评估长期可维护性。

### a. 合入安全

| 重心 | 审查问题 |
| --- | --- |
| 向前兼容 | 未明确声明 breaking change 时，默认按非破坏性改动审查，重点检查既有调用方、配置、数据、API 和行为兼容性。 |
| 正确性 | 优先找会导致错误结果、异常、数据损坏、安全风险或发布回滚的问题。 |
| 测试覆盖 | 检查变更是否覆盖关键路径、兼容场景、失败路径和回归风险。 |

### b. 可维护性

| 重心 | 审查问题 |
| --- | --- |
| 命名与可读性 | 检查命名规范、代码格式、局部复杂度、注释必要性和项目风格一致性。 |
| 简洁实现 | 发现重复、绕路或过度复杂实现时，建议更简洁、可读的方案。 |
| 抽象设计 | 代码已出现扩展苗头时，评估是否需要合适的抽象或设计模式，不为假想扩展过早设计。 |

## 0x05 输出草稿

用户说 `review`、`复查`、`代码审查` 等时，先输出对话草稿报告。

报告固定包含：

1. `汇总评论`：整体结论、风险点、是否建议合入。
2. `新增问题`：本轮新发现的问题，按 P0 / P1 / P2 排序。
3. `已存在未解决 review 线程的解决情况`：用表格输出。

既有线程表格至少包含 `评论 / 线程`、`位置`、`状态`、`处理动作`、`证据`。

状态值固定为 `已修复`、`未修复`、`待确认`。

## 0x06 线程收口

用户触发 review 后，完成逐项核对的既有未解决 review thread 可以自动处理。

| 状态 | 动作 |
| --- | --- |
| `已修复` | 自动 resolve，并在报告中标注 `resolved`。 |
| `未修复` | 保持 unresolved，并说明仍缺少的修复。 |
| `待确认` | 不自动 resolve，说明争议点或证据缺口。 |

不对本轮新增评论自动 resolve。

用户明确要求不自动 resolve 时，遵循用户要求。

## 0x07 评论规范

### a. 严重程度

严重程度顺序固定为 P0 > P1 > P2。

| 级别 | 含义 |
| --- | --- |
| `P0` | 阻塞合入，存在明确正确性、安全、数据或发布风险。 |
| `P1` | 建议修复，风险较高或会造成维护成本。 |
| `P2` | 可选优化，不阻塞但能提升质量。 |

### b. 发布位置

可定位到文件与行号的问题，必须优先发布 inline review comment。

仅当问题无法定位到单行，或工具限制无法 inline 时，退化为 conversation 评论，并注明 `path:line` 与退化原因。

行内评论格式：

```markdown
**`path/to/file.go:42`** [P1]
> return nil

问题：错误返回值未处理，可能导致空指针。
```

评论内容结构：

- 必须包含明确问题、影响范围和修复方向。
- 当对话中已经确认结构代码或关键实现形态时，PR 评论必须保留这些结构信号。
- 不要把已确认的结构方案压缩成泛化建议，导致作者无法直接落代码。

Bad：

```markdown
[P1] 问题：这里应该同时展示 events 和返回码错误。

建议：去掉早退，按并集逻辑处理。
```

Good：

```markdown
[P1] 问题：错误来源应该做并集展示。这里发现已有 exception event 就直接返回，会让同一个 span 中已经上报的标准 exception event 和 attributes.rpc.error_code / attributes.trpc.status_code 变成互斥关系；后续 get_exception_events() 只会看到原始 events，无法再补充返回码逻辑异常，错误列表、详情和接口分布都会漏掉这类返回码错误。

建议：去掉这个早退，保留已有 events，并在存在 RPC/tRPC 错误码时额外 append 一个返回码 exception event。核心逻辑可以保持很简单：events = span.get(OtlpKey.EVENTS) or [] 后写回 span[OtlpKey.EVENTS] = events，然后沿用下面的返回码提取逻辑。这里 if code is None or code == "": 建议保留，并补一句注释说明不要写成 if not code，避免数值型错误码 0 被误判为空。
```

### c. 评论语言

| 场景 | 语言 |
| --- | --- |
| 对话草稿 | 使用当前对话语言。 |
| 发布到 PR | conversation、inline review comment 和 approve body 使用目标项目 `language` 字段。 |
| 未配置语言 | 默认使用中文。 |

目标项目 `language` 字段从 `repos.json`、`private/repos.json` 读取。

## 0x08 交付自检

- 新增问题必须以风险为主，不把风格偏好伪装成阻塞问题。
- 每个 finding 都要有代码位置、影响说明和修复方向。
- 没有发现问题时，明确说明未发现阻塞问题，并列出残余风险或未覆盖检查。
- 发布到 PR 的评论必须和用户最终确认的草稿完全一致。
- 发布前逐条比对最终草稿，禁止在发布时二次改写、压缩、补充或删减。
- 发布到 PR 前再次确认 inline 评论、总结评论和语言选择。
