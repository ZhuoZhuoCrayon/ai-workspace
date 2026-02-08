# AI 工作区建设 —— 可行方案

> 基于 [README.md](./README.md) 制定。

---

## 1. 设计原则

1. **文件即协议**：所有知识、规则、状态均以 Markdown 文件存储，兼容 Cursor / Codex / Claude 等任意模型
2. **Git 即同步**：利用 Git 进行版本控制和多端同步
3. **约定优于配置**：通过目录结构约定组织内容，减少额外配置
4. **路径即描述**：文档中所有引用一律使用完整相对路径，杜绝模糊表述

---

## 2. 架构设计

### 2.1 Public / Private 可见性模型

通过 `private/` 目录 + `.gitignore` 实现公私隔离。`private/` 内部结构与公开区域**镜像对齐**。

| 维度 | 公开路径 | 私有路径 |
|------|---------|---------|
| 仓库注册 | `repos.json` | `private/repos.json` |
| 项目软链 | `projects/<project>/` | `private/projects/<project>/` |
| 知识库 | `knowledge/<project>/` | `private/knowledge/<project>/` |
| 跨项目知识 | `knowledge/_shared/` | `private/knowledge/_shared/` |
| 任务管理 | `issues/` | `private/issues/` |
| 个人空间 | — | `private/profile.md`、`private/journal/` |

**约束**：
- 创建/归档对象时通过 `visibility: public | private` 指定目标
- 所有检索操作默认同时扫描公开和私有路径

### 2.2 目录结构

```
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
│       ├── project_mgr/SKILL.md           # 项目管理（添加/删除/规范）
│       └── daily_journal/SKILL.md         # 工作日志
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
│       ├── snippets/
│       ├── troubleshooting/
│       └── guides/
│
├── projects/                              # 公开项目（均为软链接）
│   └── <project>/ → /path/to/local/repo
│
├── issues/                                # 公开任务管理
│   ├── INDEX.md
│   └── <YYYY-MM-DD-title>/
│       ├── README.md
│       ├── PLAN.md
│       └── PROGRESS.md
│
└── private/                               # 私有空间（.gitignore 忽略）
    ├── repos.json
    ├── profile.md                         # AI 分身配置
    ├── journal/
    ├── knowledge/                         # 结构同 knowledge/
    ├── projects/
    └── issues/
```

### 2.3 知识继承机制

模型处理项目任务时的知识查找顺序（以 `project-a` 为例）：

```
1. 会话上下文
2. 任务上下文 → issues/<YYYY-MM-DD-title>/
3. 项目自身   → projects/project-a/AGENTS.md、projects/project-a/.cursor/rules/
4. 项目知识库 → knowledge/project-a/ + private/knowledge/project-a/
5. 通用知识   → knowledge/_shared/ + private/knowledge/_shared/
6. 工作区全局 → AGENTS.md、.cursor/rules/、.cursor/skills/
```

---

## 3. 多仓库管理

所有外部项目统一通过**软链接**接入，仓库元信息记录在 `repos.json` / `private/repos.json`。

### 3.1 repos.json 格式

```json
[
  {
    "name": "project-a",
    "description": "后端微服务",
    "git_url": "https://github.com/user/project-a.git",
    "branch": "main",
    "local_path": "/Users/user/code/project-a"
  }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 项目名，对应 `projects/<name>/` 软链目录名 |
| `description` | string | 项目简述 |
| `git_url` | string | Git 远程地址 |
| `branch` | string | 主分支名 |
| `local_path` | string | 本地仓库绝对路径（软链目标） |

---

## 4. Skills 设计

工作区包含三个 Skill，职责边界清晰：

| Skill             | 路径                                      | 职责                                                           |
|-------------------|-----------------------------------------|--------------------------------------------------------------|
| **knowledge_mgr** | `.cursor/skills/knowledge_mgr/SKILL.md` | 知识对象（issue / plan / snippet / troubleshooting）的模板、创建、归档、索引更新 |
| **project_mgr**   | `.cursor/skills/project_mgr/SKILL.md`   | 项目的添加、删除、项目规范                                                |
| **daily_journal** | `.cursor/skills/daily_journal/SKILL.md` | 创建 `private/journal/<YYYY-MM-DD>.md`，汇总当天 git commits 和任务进度  |

### 4.1 knowledge_mgr

统一管理四类知识对象的全生命周期：创建 → 归档 → 索引。

#### 管理的对象类型

| 对象 | 创建位置 | 归档位置 |
|------|---------|---------|
| issue | `issues/<YYYY-MM-DD-title>/README.md` | — （原地创建，无需归档） |
| plan | `issues/<YYYY-MM-DD-title>/PLAN.md` | — （原地创建，无需归档） |
| snippet | `knowledge/_inbox/` 或直接放入目标目录 | `knowledge/<project>/snippets/` |
| troubleshooting | `knowledge/_inbox/` 或直接放入目标目录 | `knowledge/<project>/troubleshooting/` |

#### 创建流程

```
用户说 "创建一个 issue / plan / snippet / troubleshooting"
  │
  ├─ issue → 创建 issues/<YYYY-MM-DD-title>/README.md（按模板填充）
  │          更新 issues/INDEX.md
  │
  ├─ plan  → 读取 issues/<YYYY-MM-DD-title>/README.md
  │          查找 knowledge/<project>/ 相关知识
  │          生成 issues/<YYYY-MM-DD-title>/PLAN.md（按模板填充）
  │
  └─ snippet / troubleshooting
             → 按模板创建到 knowledge/<project>/<type>/
             → 更新三级索引
```

#### 归档流程（Inbox 模式）

```
knowledge/_inbox/ 中有待归档文档
  │
  ├─ 读取文档内容
  ├─ 判断项目归属（<project> / _shared）
  ├─ 判断对象类型（snippet / troubleshooting）
  ├─ 补全 frontmatter
  ├─ 移动到 knowledge/<project>/<type>/
  └─ 更新三级 → 二级 → 一级索引
```

私有文档同理，丢入 `private/knowledge/_inbox/` 即可。

#### 三级索引体系

```
knowledge/INDEX.md                     ← 一级：所有项目知识概览
knowledge/<project>/INDEX.md           ← 二级：某项目各分类概览
knowledge/<project>/snippets/INDEX.md  ← 三级：某分类下文件详情
```

INDEX.md 是**可重建的**，由 AI 根据目录内容自动生成，人类不需要手动编辑。

三级索引格式：

```markdown
| 文件 | 标签 | 摘要 | 更新日期 |
|------|------|------|---------|
| [标题](./文件名.md) | `tag1` `tag2` | 一句话摘要 | YYYY-MM-DD |
```

`issues/INDEX.md` 和 `private/issues/INDEX.md` 同理维护。

#### 文档模板

所有知识对象使用统一的 frontmatter + 正文结构。

**排障经验模板**

```markdown
---
title: <标题>
tags: [<标签1>, <标签2>]
description: <一句话总结>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
---

# <标题>

## 0x01 关键信息

### a. 现象

### b. 环境

### c. 根因

## 0x02 排查过程

## 0x03 解决方案

## 0x04 参考
```

**代码片段模板**

```markdown
---
title: <标题>
tags: [<标签1>, <标签2>]
description: <一句话总结>
language: <go|python|typescript|...>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
---

# <标题>

## 0x01 关键信息

### a. 适用场景

## 0x02 代码片段

### a. 代码示例-1

\```<language>
// 代码内容
\```

### b. 代码示例-2

...
```

**Issue README 模板**

```markdown
---
title: <标题>
tags: [<标签1>, <标签2>]
description: <一句话总结>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
---

# <任务标题>

## 0x01 背景

### a. Why

### b. 目标

## 0x02 实现路线

### a. 建议的方案

### b. 约束

## 0x03 参考
```

**PLAN 模板**

```markdown
---
title: <标题>
tags: [<标签1>, <标签2>]
issue: <关联的 issue 路径>
description: <一句话总结>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
---

# <任务标题> —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 调研

### a. 竞品-1

### b. 业界最佳实践

## 0x02 方案设计

## 0x03 实施步骤

### a. 阶段拆分

### b. 阶段一 - xxx

### c. 阶段二 - xxx

## 0x04 参考

---
*制定日期：<YYYY-MM-DD>*
```

### 4.2 project_mgr

管理项目的接入和移除。

#### 添加项目

```
1. 确认参数：name / local_path / git_url / branch / visibility
2. 创建软链接
   · public  → ln -s <local_path> projects/<name>
   · private → ln -s <local_path> private/projects/<name>
3. 追加到 repos.json 或 private/repos.json
4. 创建 knowledge/<name>/INDEX.md（或 private/knowledge/<name>/INDEX.md）
5. 若 projects/<name>/AGENTS.md 不存在，提示用户创建
6. 更新 knowledge/INDEX.md
```

#### 删除项目

```
1. 删除软链接 projects/<name> 或 private/projects/<name>
2. 从 repos.json 或 private/repos.json 中移除对应条目
3. 提示用户是否同时删除 knowledge/<name>/（默认保留）
```

### 4.3 Skills 与文档的边界

- **Skill** = 操作流程（"怎么做"），模型读完后执行动作
- **文档** = 参考知识（"是什么"），模型读完后理解并引用

演进路径：**先写文档 → 重复当作操作手册使用 → 提取为 Skill**。

---

## 5. AI 交互设计

### 5.1 AGENTS.md 核心内容

```markdown
# AI 工作区指引

## 工作区结构
- repos.json / private/repos.json：仓库注册表
- projects/ / private/projects/：项目软链接
- knowledge/ / private/knowledge/：知识库（按项目隔离）
- issues/ / private/issues/：任务管理
- .cursor/skills/：工作区 Skill
- .cursor/rules/：工作区 Rules

## 知识检索规则
检索知识和仓库时，必须同时扫描公开和私有路径。

## 任务处理流程
1. 阅读 issues/<date-title>/README.md
2. 查找 knowledge/<project>/ 和 projects/<project>/AGENTS.md
3. 制定 issues/<date-title>/PLAN.md
4. 执行实施
5. 更新 issues/<date-title>/PROGRESS.md
```

### 5.2 AI 分身配置（`private/profile.md`）

```markdown
# AI 分身配置

## 基本信息
- 姓名：Crayon
- 角色：全栈开发工程师

## 技术栈
- 主力语言：Go, TypeScript, Python

## 长期记忆
（由 AI 在交互过程中持续更新）
- 2026-02-06：启动 AI 工作区项目
```

---

## 6. 实施计划

### Phase 1：基础框架搭建（1~2 天）

- [ ] 创建目录结构（含 `knowledge/_inbox/`、`private/`）
- [ ] 编写 `.gitignore`、`repos.json`、`private/repos.json`
- [ ] 编写 `AGENTS.md` 和 `CLAUDE.md`
- [ ] 配置 `.cursor/rules/`
- [ ] 编写三个 Skill：`knowledge_mgr`、`project_mgr`、`daily_journal`
- [ ] 提交首个 Git commit

### Phase 2：知识库初始化（3~5 天）

- [ ] 确定项目列表，创建 `knowledge/<project>/` 目录
- [ ] 迁移现有代码片段到 `knowledge/<project>/snippets/`
- [ ] 迁移排障经验到 `knowledge/<project>/troubleshooting/`
- [ ] 通过 `knowledge_mgr` 生成各级索引

### Phase 3：多项目接入（1~2 天）

- [ ] 通过 `project_mgr` 接入 1~2 个试点项目
- [ ] 验证知识继承机制

### Phase 4：持续迭代

- [ ] 完善 `private/profile.md`
- [ ] 探索基于 OpenClaw 的 AI 分身集成

---

*制定日期：2026-02-08*
*状态：待评审*
