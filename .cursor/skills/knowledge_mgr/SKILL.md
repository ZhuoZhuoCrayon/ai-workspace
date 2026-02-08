---
name: knowledge-mgr
title: knowledge_mgr — 知识管理
description: 创建、归档和索引知识对象（issue、plan、snippet、troubleshooting）。当用户想要创建任务/issue、编写计划、记录代码片段或排障经验、归档收件箱文档或更新知识索引时使用。
---

# knowledge_mgr — 知识管理

管理四类知识对象的创建、归档和索引：issue / plan / snippet / troubleshooting。

所有操作支持 `visibility: public | private`，private 对象路径前缀为 `private/`，默认归档到 `public`。

## 0x01 对象与位置

所有知识对象均归属于项目，存放在 `knowledge/<project>/` 下：

| 对象              | 位置                                                    |
|-----------------|-------------------------------------------------------|
| issue           | `knowledge/<project>/issues/<YYYY-MM-DD-title>/README.md` |
| plan            | `knowledge/<project>/issues/<YYYY-MM-DD-title>/PLAN.md`   |
| snippet         | `knowledge/<project>/snippets/`                        |
| troubleshooting | `knowledge/<project>/troubleshooting/`                 |

## 0x02 创建流程

### a. Issue

1. 确认标题、关联项目、visibility
2. 目录名：`<YYYY-MM-DD-title>`（title 用小写英文短横线）
3. 按 [templates.md](templates.md) 中的 Issue README 模板创建 `knowledge/<project>/issues/<YYYY-MM-DD-title>/README.md`
4. 更新索引（二级 → 一级）

### b. Plan

1. 读取关联的 `knowledge/<project>/issues/<YYYY-MM-DD-title>/README.md`
2. 检索 `knowledge/<project>/` + `private/knowledge/<project>/` 相关知识
3. 按 [templates.md](templates.md) 中的 PLAN 模板生成 `knowledge/<project>/issues/<YYYY-MM-DD-title>/PLAN.md`

### c. Snippet / Troubleshooting

1. 确认标题、关联项目、visibility
2. 文件名：小写英文短横线 `.md`
3. 按 [templates.md](templates.md) 对应模板创建文件
4. 更新索引（三级 → 二级 → 一级）

## 0x03 归档流程（Inbox）

处理 `knowledge/_inbox/` 或 `private/knowledge/_inbox/` 中的待归档文档：

1. 读取文档内容
2. 判断项目归属（`<project>` / `_shared`）和对象类型
3. 补全 frontmatter（title / tags / description / created / updated）
4. 移动到 `knowledge/<project>/<type>/`
5. 更新索引（三级 → 二级 → 一级）
6. 确认后删除 inbox 源文件

## 0x04 索引更新

### a. 三级索引体系

```text
knowledge/INDEX.md                     ← 一级：项目知识概览
knowledge/<project>/INDEX.md           ← 二级：分类概览（含 issues、snippets、troubleshooting 等）
knowledge/<project>/snippets/INDEX.md  ← 三级：文件详情
```

### b. 更新步骤

1. 读取目标目录下所有 `.md`（排除 `INDEX.md`）
2. 提取 frontmatter：`title` / `tags` / `description` / `updated`；无 frontmatter 则从标题和内容推断
3. 按更新时间倒序生成 INDEX.md
4. 向上逐级更新

### c. 索引格式

**三级**（`knowledge/<project>/snippets/INDEX.md`）：

```markdown
| 文件 | 标签 | 摘要 | 更新日期 |
|------|------|------|---------|
| [标题](./文件名.md) | `tag1` `tag2` | 一句话摘要 | YYYY-MM-DD |
```

**二级**（`knowledge/<project>/INDEX.md`）：

```markdown
| 分类 | 路径 | 数量 | 说明 |
|------|------|------|------|
| Issues | [issues/](./issues/) | N 篇 | ... |
| 代码片段 | [snippets/](./snippets/INDEX.md) | N 篇 | ... |
```

**一级**（`knowledge/INDEX.md`）：

```markdown
| 项目 | 路径 | 数量 | 说明 |
|------|------|------|------|
| 通用知识 | [_shared/](./_shared/INDEX.md) | N 篇 | ... |
```

## 0x05 模板

所有文档模板见 [templates.md](templates.md)，包含：
- 排障经验模板
- 代码片段模板
- Issue README 模板
- PLAN 模板

**创建文档时，必须先阅读 [templates.md](templates.md) 获取完整模板结构，然后严格按照模板格式和 `.cursor/rules/markdown.mdc` 规范编写内容。**

