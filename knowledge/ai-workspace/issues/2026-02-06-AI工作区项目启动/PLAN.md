---
title: AI 工作区建设 —— 实施方案
tags: [ai-workspace, 规划, 架构]
issue: knowledge/ai-workspace/issues/2026-02-06-AI工作区项目启动/README.md
description: AI 工作区的架构设计、Skills 设计和实施计划
created: 2026-02-08
updated: 2026-02-09
---

# AI 工作区建设 —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 设计原则

1. **文件即协议**：所有知识、规则、状态均以 Markdown 文件存储，兼容 Cursor / Codex / Claude 等任意模型
2. **Git 即同步**：利用 Git 进行版本控制和多端同步
3. **约定优于配置**：通过目录结构约定组织内容，减少额外配置
4. **路径即描述**：文档中所有引用一律使用完整相对路径，杜绝模糊表述

## 0x02 架构设计

### a. Public / Private 可见性模型

通过 `private/` 目录 + `.gitignore` 实现公私隔离。`private/` 内部结构与公开区域**镜像对齐**。

| 维度       | 公开路径                    | 私有路径                            |
|----------|-------------------------|-----------------------------------|
| 仓库注册     | `repos.json`            | `private/repos.json`              |
| 知识库      | `knowledge/<project>/`  | `private/knowledge/<project>/`    |
| 跨项目知识    | `knowledge/_shared/`    | `private/knowledge/_shared/`      |
| 个人空间     | —                       | `private/profile.md`、`private/journal/` |

**约束**：

- 创建/归档对象时通过 `visibility: public | private` 指定目标
- 所有检索操作默认同时扫描公开和私有路径

### b. 目录结构

```text
ai-workspace/
├── AGENTS.md                              # 工作区级 AI 指引
├── CLAUDE.md                              # 工作区级 Claude 指引
├── .gitignore                             # 含 private/ 忽略规则
├── repos.json                             # 公开仓库注册表
│
├── .cursor/
│   ├── rules/                             # 全局规则
│   │   ├── general.mdc
│   │   ├── markdown.mdc
│   │   └── git.mdc
│   └── skills/                            # 全局技能
│       ├── knowledge_mgr/SKILL.md         # 知识管理（创建/归档/索引）
│       └── project_mgr/SKILL.md           # 项目管理（添加/删除/规范）
│
├── knowledge/                             # 公开知识库（按项目隔离）
│   ├── INDEX.md                           # 一级汇总索引
│   ├── _inbox/                            # 待归档收件箱
│   ├── _shared/                           # 跨项目通用知识
│   │   ├── INDEX.md
│   │   ├── snippets/
│   │   ├── guides/
│   │   └── troubleshooting/
│   └── <project>/                         # 某项目的知识
│       ├── INDEX.md
│       ├── issues/                        # 项目任务（issue + plan）
│       │   └── <YYYY-MM-DD-title>/
│       │       ├── README.md
│       │       ├── PLAN.md
│       │       └── PROGRESS.md
│       ├── snippets/
│       ├── troubleshooting/
│       └── guides/
│
└── private/                               # 私有空间（.gitignore 忽略）
    ├── repos.json
    ├── profile.md                         # AI 分身配置
    ├── journal/
    └── knowledge/                         # 结构同 knowledge/
```

### c. 项目访问方式

外部项目通过 `repos.json` / `private/repos.json` 注册，`local_path` 字段记录本地仓库绝对路径。模型处理项目任务时：

1. 从 `repos.json` / `private/repos.json` 读取 `local_path`
2. 通过 `cd <local_path>` 切换到项目目录进行代码开发
3. 同时加载 `knowledge/<project>/` 下的项目知识库作为上下文

> **设计决策**：早期方案使用软链接（`projects/<name>/ → local_path`）挂载项目，实践中发现 `local_path` 已足够定位项目源码，软链接增加了维护成本且对模型无额外收益，因此取消。

### d. 知识继承机制

模型处理项目任务时的知识查找顺序（以 `bkmonitor` 为例）：

```text
1. 会话上下文
2. 任务上下文   → knowledge/bkmonitor/issues/<YYYY-MM-DD-title>/
3. 项目自身     → <local_path>/AGENTS.md、<local_path>/.cursor/rules/
4. 项目知识库   → knowledge/bkmonitor/ + private/knowledge/bkmonitor/
5. 通用知识     → knowledge/_shared/ + private/knowledge/_shared/
6. 工作区全局   → AGENTS.md、.cursor/rules/、.cursor/skills/
```

## 0x03 多仓库管理

### a. repos.json 格式

```json
[
  {
    "name": "bkmonitor",
    "description": "蓝鲸监控平台 (bk-monitor/bkmonitor)",
    "git_url": "https://github.com/TencentBlueKing/bk-monitor.git",
    "branch": "master",
    "local_path": "/Users/user/bk-monitor/bkmonitor"
  }
]
```

| 字段            | 类型     | 说明                 |
|---------------|--------|--------------------|
| `name`        | string | 项目名，对应 `knowledge/<name>/` 知识目录 |
| `description` | string | 项目简述               |
| `git_url`     | string | Git 远程地址           |
| `branch`      | string | 主分支名               |
| `local_path`  | string | 本地仓库绝对路径           |

### b. 添加项目流程

```text
1. 确认参数：name / local_path / visibility
2. 自动发现 git_url、branch
3. 追加到 repos.json 或 private/repos.json
4. 创建 knowledge/<name>/INDEX.md
5. 更新 knowledge/INDEX.md
```

### c. 删除项目流程

```text
1. 从 repos.json 或 private/repos.json 中移除对应条目
2. 询问用户是否删除 knowledge/<name>/（默认保留）
3. 更新 knowledge/INDEX.md
```

## 0x04 Skills 设计

工作区包含两个 Skill，职责边界清晰：

| Skill             | 路径                                      | 职责                                      |
|-------------------|-----------------------------------------|-----------------------------------------|
| **knowledge_mgr** | `.cursor/skills/knowledge_mgr/SKILL.md` | 知识对象的模板、创建、归档、索引更新                      |
| **project_mgr**   | `.cursor/skills/project_mgr/SKILL.md`   | 项目的添加、删除、项目规范                           |

### a. knowledge_mgr

统一管理四类知识对象的全生命周期：创建 → 归档 → 索引。

**管理的对象类型**

| 对象              | 位置                                                         |
|-----------------|-----------------------------------------------------------|
| issue           | `knowledge/<project>/issues/<YYYY-MM-DD-title>/README.md` |
| plan            | `knowledge/<project>/issues/<YYYY-MM-DD-title>/PLAN.md`   |
| snippet         | `knowledge/<project>/snippets/`                           |
| troubleshooting | `knowledge/<project>/troubleshooting/`                    |

**创建流程**

```text
用户说 "创建一个 issue / plan / snippet / troubleshooting"
  │
  ├─ issue → 创建 knowledge/<project>/issues/<YYYY-MM-DD-title>/README.md
  │          更新 knowledge/<project>/INDEX.md
  │
  ├─ plan  → 读取 knowledge/<project>/issues/<YYYY-MM-DD-title>/README.md
  │          检索 knowledge/<project>/ 相关知识
  │          生成 knowledge/<project>/issues/<YYYY-MM-DD-title>/PLAN.md
  │
  └─ snippet / troubleshooting
             → 按模板创建到 knowledge/<project>/<type>/
             → 更新三级索引
```

**归档流程（Inbox 模式）**

```text
knowledge/_inbox/ 中有待归档文档
  │
  ├─ 读取文档内容
  ├─ 判断项目归属（<project> / _shared）
  ├─ 判断对象类型（snippet / troubleshooting）
  ├─ 补全 frontmatter
  ├─ 移动到 knowledge/<project>/<type>/
  └─ 更新三级 → 二级 → 一级索引
```

**三级索引体系**

```text
knowledge/INDEX.md                     ← 一级：所有项目知识概览
knowledge/<project>/INDEX.md           ← 二级：某项目各分类概览
knowledge/<project>/snippets/INDEX.md  ← 三级：某分类下文件详情
```

INDEX.md 是**可重建的**，由 AI 根据目录内容自动生成。

**文档模板**

所有知识对象使用统一的 frontmatter + 正文结构，模板定义在 `.cursor/skills/knowledge_mgr/templates.md`。

### b. project_mgr

管理项目的注册和移除，通过 `repos.json` 记录项目元信息。详见 0x03 多仓库管理。

### c. Skills 与文档的边界

- **Skill** = 操作流程（"怎么做"），模型读完后执行动作
- **文档** = 参考知识（"是什么"），模型读完后理解并引用

演进路径：**先写文档 → 重复当作操作手册使用 → 提取为 Skill**。

## 0x05 AI 交互设计

### a. AGENTS.md

工作区级 AI 指引，包含：工作区结构、通用规范、知识检索规则、项目访问方式、知识继承顺序、任务处理流程。

所有模型（Cursor / Codex / Claude）读取后即可理解工作区约定并正确执行任务。

### b. AI 分身配置

`private/profile.md` 记录 AI 分身的基本信息、技术栈偏好和长期记忆，由 AI 在交互中持续更新。

## 0x06 实施计划与进展

### a. Phase 1：基础框架搭建

| 任务                                        | 状态 |
|-------------------------------------------|:--:|
| 创建目录结构（含 `knowledge/_inbox/`、`private/`） | 已完成 |
| 编写 `.gitignore`、`repos.json`、`private/repos.json` | 已完成 |
| 编写 `AGENTS.md` 和 `CLAUDE.md`             | 已完成 |
| 配置 `.cursor/rules/`（general / markdown / git） | 已完成 |
| 编写 `knowledge_mgr` Skill                 | 已完成 |
| 编写 `project_mgr` Skill                   | 已完成 |
| 提交首个 Git commit                          | 待完成 |

### b. Phase 2：知识库初始化

| 任务                                     | 状态 |
|----------------------------------------|:--:|
| 确定项目列表，创建 `knowledge/<project>/` 目录    | 已完成 |
| 迁移现有代码片段到 `knowledge/<project>/snippets/` | 待完成 |
| 迁移排障经验到 `knowledge/<project>/troubleshooting/` | 待完成 |
| 通过 `knowledge_mgr` 生成各级索引              | 部分完成 |

### c. Phase 3：多项目接入

| 任务                           | 状态 |
|------------------------------|:--:|
| 通过 `project_mgr` 接入试点项目     | 已完成 |
| 验证知识继承机制                     | 已完成 |

已接入项目：

- `bkmonitor`（公开）— 蓝鲸监控平台
- `ai-workspace`（公开）— 本工作区
- `bkm-skills`（私有）— BlueKing Monitor Skills

### d. Phase 4：持续迭代

| 任务                          | 状态 |
|-----------------------------|:--:|
| 完善 `private/profile.md`    | 待完成 |
| 探索基于 OpenClaw 的 AI 分身集成    | 待完成 |
| 清理历史遗留目录（`projects/` 等）     | 待完成 |

### e. 迭代记录

| 日期         | 变更内容                                    |
|------------|-------------------------------------------|
| 2026-02-08 | 初版方案制定                                  |
| 2026-02-09 | 取消软链接方案，改用 `repos.json` + `local_path` 访问项目 |
| 2026-02-09 | 取消根目录 `issues/`，issue 归入 `knowledge/<project>/issues/` |
| 2026-02-09 | 全局 Markdown 规范审计与修复                     |

---

*制定日期：2026-02-08*
*最后更新：2026-02-09*
*状态：已归档*
