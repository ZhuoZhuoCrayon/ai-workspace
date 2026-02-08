# knowledge_mgr — 知识管理

统一管理四类知识对象的创建、归档和索引：issue / plan / snippet / troubleshooting。

## 触发方式

| 用户指令 | 执行动作 |
|---------|---------|
| "创建一个 issue" | 创建 issue |
| "为这个任务制定方案" | 创建 plan |
| "记录这个代码片段" | 创建 snippet |
| "记录这个排障经验" | 创建 troubleshooting |
| "归档 inbox 中的文档" | 执行归档流程 |
| "更新 xxx 的索引" | 更新索引 |

## 对象类型与位置

| 对象 | 创建位置 | 归档位置 |
|------|---------|---------|
| issue | `issues/<YYYY-MM-DD-title>/README.md` | — （原地创建） |
| plan | `issues/<YYYY-MM-DD-title>/PLAN.md` | — （原地创建） |
| snippet | 直接创建或 `knowledge/_inbox/` | `knowledge/<project>/snippets/` |
| troubleshooting | 直接创建或 `knowledge/_inbox/` | `knowledge/<project>/troubleshooting/` |

> 私有对象同理，前缀替换为 `private/`。

## 创建流程

### 创建 Issue

1. 确认：标题、关联项目、`visibility`（public / private）
2. 目录名格式：`<YYYY-MM-DD-title>`（title 用小写英文短横线）
3. 按 visibility 创建目录：`issues/<YYYY-MM-DD-title>/` 或 `private/issues/<YYYY-MM-DD-title>/`
4. 按 **Issue README 模板** 创建 `README.md`
5. 更新 `issues/INDEX.md` 或 `private/issues/INDEX.md`

### 创建 Plan

1. 读取关联的 `issues/<YYYY-MM-DD-title>/README.md`
2. 在 `knowledge/` 和 `private/knowledge/` 中查找相关项目的知识
3. 按 **PLAN 模板** 生成 `issues/<YYYY-MM-DD-title>/PLAN.md`

### 创建 Snippet / Troubleshooting

1. 确认：标题、关联项目、`visibility`
2. 目标目录：`knowledge/<project>/<type>/` 或 `private/knowledge/<project>/<type>/`
3. 文件名格式：小写英文短横线 `.md`
4. 按对应模板创建文件
5. 更新三级索引 → 二级索引 → 一级索引

## 归档流程（Inbox 模式）

当 `knowledge/_inbox/` 或 `private/knowledge/_inbox/` 中有待归档文档时：

1. 逐个读取文档内容
2. 判断项目归属（`<project>` / `_shared`）
3. 判断对象类型（snippet / troubleshooting）
4. 补全 frontmatter（title / tags / description / created / updated）
5. 移动到目标目录
6. 更新三级 → 二级 → 一级索引
7. 确认后删除已处理的 inbox 源文件

## 索引更新

### 三级索引体系

```
knowledge/INDEX.md                     ← 一级：所有项目知识概览
knowledge/<project>/INDEX.md           ← 二级：某项目各分类概览
knowledge/<project>/snippets/INDEX.md  ← 三级：某分类下文件详情
```

`issues/INDEX.md` 和 `private/issues/INDEX.md` 也由本 Skill 维护。

### 更新步骤

1. 读取目标目录下所有 `.md` 文件（排除 `INDEX.md`）
2. 提取 frontmatter 中的 `title`、`tags`、`description`、`updated`
3. 若无 frontmatter，从一级标题提取 title，从内容推断 tags
4. 按更新时间倒序排列
5. 生成 INDEX.md（格式见下方）
6. 向上逐级更新（三级 → 二级 → 一级）

### 索引格式

**三级索引**（如 `knowledge/<project>/snippets/INDEX.md`）：

```markdown
| 文件 | 标签 | 摘要 | 更新日期 |
|------|------|------|---------|
| [标题](./文件名.md) | `tag1` `tag2` | 一句话摘要 | YYYY-MM-DD |
```

**二级索引**（如 `knowledge/<project>/INDEX.md`）：

```markdown
| 分类 | 路径 | 数量 | 说明 |
|------|------|------|------|
| 代码片段 | [snippets/](./snippets/INDEX.md) | N 篇 | 可复用的代码片段 |
```

**一级索引**（`knowledge/INDEX.md`）：

```markdown
| 项目 | 路径 | 数量 | 说明 |
|------|------|------|------|
| 通用知识 | [_shared/](./_shared/INDEX.md) | N 篇 | 跨项目通用知识 |
```

## 文档模板

### 排障经验模板

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

### 代码片段模板

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
// code
\```
```

### Issue README 模板

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

### PLAN 模板

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

## 0x02 方案设计

## 0x03 实施步骤

## 0x04 参考

---
*制定日期：<YYYY-MM-DD>*
```
