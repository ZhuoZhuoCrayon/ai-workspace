---
name: project-mgr
title: project_mgr — 项目管理
description: 通过 repos.json 注册和管理工作区中的项目。当用户想要接入项目到工作区、移除项目或询问项目设置规范时使用。
---

# project_mgr — 项目管理

管理工作区中项目的添加和删除。默认 visibility 为 `public`。

项目通过 `repos.json` / `private/repos.json` 注册，`local_path` 记录本地仓库绝对路径，模型可通过该路径 `cd` 到项目目录进行开发。

## 0x01 添加项目

### a. 输入参数

| 参数         | 必填 | 说明                                   |
|------------|----|-----------------------------------------|
| local_path | 是  | 本地路径（仓库根目录或大仓子目录均可）              |
| visibility | 否  | public（默认） / private                   |
| name       | 否  | 项目名称覆盖（默认从 `local_path` 的 basename 推断） |
| language   | 否  | 项目语言偏好：`zh`（默认） / `en`，影响 PR review 评论、commit message 等交互语言 |

### b. 自动发现

先 `cd` 到 `local_path`，再**逐条**执行以下 Git 命令采集信息（Git 在子目录中会自动向上查找 `.git`）：

| 信息       | 命令                                                        | 说明                                           |
|----------|-----------------------------------------------------------|----------------------------------------------|
| 远程仓库地址   | `git remote -v`                                           | 优先取 `upstream`（fetch），其次 `origin`（fetch）       |
| 默认分支     | `git symbolic-ref refs/remotes/<remote>/HEAD 2>/dev/null` | 失败则回退检测 `master` / `main` 分支是否存在              |
| 仓库描述     | `gh repo view <owner>/<repo> --json description -q .description`（可用时） | GH 描述优先；若不可用，回退本地 `README.md` 首段摘要 |

推断规则：

- **local_path**：直接使用用户提供的路径，不回退到仓库根目录（大仓场景下用户只关心子目录）
- **项目名称**：取 `local_path` 的 basename（如 `/path/bk-monitor/bkmonitor` → `bkmonitor`）；用户可通过 `name` 参数覆盖
- **远程仓库地址**：如果包含 token 或凭据（如 `https://user:token@github.com/...`），需要**剔除凭据**后再记录，格式化为 `https://github.com/<owner>/<repo>.git`
- **仓库描述（description）补齐策略**（不能为空）：
  1. 优先使用 Git 平台描述（GitHub/GHE，`gh repo view` 或 API）。
  2. 若平台不可达或描述为空，回退读取 `<local_path>/README.md`：取首个 `#` 标题后第一段非空正文作为摘要。
  3. 若仍为空，使用简短占位描述：`<name> 项目仓库`，并在回复中标注“建议后续人工完善”。

### c. 确认

将自动发现的信息汇总后向用户确认，格式示例：

```text
即将添加项目：
- 名称：bkmonitor
- 本地路径：/Users/xxx/bk-monitor/bkmonitor
- 远程仓库：https://github.com/TencentBlueKing/bk-monitor.git
- 默认分支：master
- 可见性：public
- 语言偏好：zh

是否确认？
```

用户确认后再执行写入操作。

### d. 执行步骤

1. 追加到 `repos.json`（或 `private/repos.json`）：

```json
{
  "name": "<name>",
  "description": "<description>",
  "git_url": "<git_url>",
  "branch": "<branch>",
  "local_path": "<local_path>",
  "language": "<language>"
}
```

> 当执行“项目巡检/配置治理”时，允许对现有 registry 做 description 补齐（仅更新空描述字段，不改动其他字段）。

2. 创建 `knowledge/<name>/INDEX.md`（或 `private/knowledge/<name>/INDEX.md`）
3. 更新 `knowledge/INDEX.md`

## 0x02 删除项目

### a. 输入参数

| 参数         | 必填 | 说明                   |
|------------|----|-----------------------|
| name       | 是  | 项目名称                 |
| visibility | 否  | public（默认） / private |

### b. 执行步骤

1. 从 `repos.json` 或 `private/repos.json` 中移除对应条目
2. 询问用户是否删除 `knowledge/<name>/`（默认保留）
3. 更新 `knowledge/INDEX.md`

## 0x03 使用项目

模型在处理项目相关任务时：

1. 从 `repos.json` / `private/repos.json` 读取 `local_path`
2. 通过 `cd <local_path>` 切换到项目目录进行代码开发
3. 同时加载 `knowledge/<name>/` 下的项目知识库作为上下文

> **关键**：`local_path` 使模型能直接访问项目源码，`knowledge/<name>/` 提供项目级知识。两者结合即可完成项目任务，无需软链接。

## 0x04 项目规范

接入的项目建议包含以下文件：

| 文件                | 作用                   |
|-------------------|----------------------|
| `AGENTS.md`       | 项目级 AI 指引（技术栈、架构、约定） |
| `.cursor/rules/`  | 项目级 Cursor Rules     |
| `.cursor/skills/` | 项目级 Cursor Skills    |
