---
name: knowledge-mgr
title: knowledge_mgr — 知识管理
description: 创建、更新、归档和索引知识对象（issue、plan、snippet、troubleshooting）。当用户想要创建任务/issue、编写计划/实施方案、记录代码片段或排障经验、修改/更新已有知识文档、归档收件箱文档或更新知识索引时使用。
---

# knowledge_mgr — 知识管理

管理四类知识对象的创建、更新、归档和索引：issue / plan / snippet / troubleshooting。

所有操作支持 `visibility: public | private`，private 对象路径前缀为 `private/`，默认为 `public`。

**核心规则：任何对知识文件的变更（创建、更新、归档）都必须执行「0x03 后置检查」。**

## 0x01 对象与位置

所有知识对象均归属于项目，存放在 `knowledge/<project>/` 下：

| 对象              | 位置                                    | 命名规则        | 模板                      |
|-----------------|---------------------------------------|-------------|-------------------------|
| issue           | `issues/<YYYY-MM-DD-title>/README.md` | 目录名：小写英文短横线 | Issue（需求）模板             |
| plan            | `issues/<YYYY-MM-DD-title>/PLAN.md`   | 同 issue 目录  | Plan（计划/实施方案）模板         |
| snippet         | `snippets/<title>.md`                 | 文件名：小写英文短横线 | Snippet（代码片段）模板         |
| troubleshooting | `troubleshooting/<title>.md`          | 文件名：小写英文短横线 | Troubleshooting（排障经验）模板 |

> 模板详见 [templates.md](templates.md)。创建文档时必须先阅读模板获取完整结构，并遵循 `.cursor/rules/markdown.mdc` 规范。

命名规则补充：

- 仅使用小写字母、数字与短横线，禁止空格与下划线
- 中文标题需转写为英文短语（必要时用拼音），确保可读且稳定
- 避免无意义缩写，优先表达问题域或功能点

所有知识文件必须包含以下 frontmatter 字段：

| 字段          | 必填 | 说明                  |
|-------------|----|---------------------|
| title       | 是  | 文档标题                |
| tags        | 是  | 标签数组，如 `[k8s, ops]` |
| description | 是  | 一句话摘要               |
| language    | 否  | 仅 snippet，代码语言      |
| issue       | 否  | 仅 plan，关联 issue 路径  |
| created     | 是  | 创建日期，`YYYY-MM-DD`   |
| updated     | 是  | 最后更新日期，`YYYY-MM-DD` |

## 0x02 操作流程

### a. 创建

1. 确认标题、关联项目、visibility
2. 判断可见性：涉及个人/敏感信息用 `private`，其余用 `public`
3. 按上表中的模板和命名规则创建文件

> Plan 额外前置：创建前先读取关联 issue 的 README.md，检索 `knowledge/<project>/` + `private/knowledge/<project>/` 相关知识。

### b. 更新

1. 读取目标文件与相关上下文
2. 按需修改内容并保持结构完整
3. 同步维护 frontmatter（尤其是 `updated` 与 `tags`）
4. 执行「0x03 后置检查」

### c. 归档（Inbox）

处理 `knowledge/_inbox/` 或 `private/knowledge/_inbox/` 中的待归档文档：

1. 读取文档内容，判断项目归属和对象类型
2. 补全 frontmatter（title / tags / description / created / updated）
3. 移动到目标位置
4. 确认后删除 inbox 源文件

## 0x03 后置检查

**任何知识文件变更后，逐项执行：**

1. **Frontmatter 维护**：确保 `updated` 为当天日期，`tags` 与内容一致
2. **索引更新**：从变更文件所在层级向上逐级更新（参照「0x04 索引体系」）
3. **自检**：确认索引中的标签、摘要、日期与文件 frontmatter 一致

## 0x04 索引体系

### a. 三级结构

```text
knowledge/INDEX.md                         ← 一级：项目知识概览
knowledge/<project>/INDEX.md               ← 二级：分类概览（含 issues、snippets、troubleshooting 等）
knowledge/<project>/issues/INDEX.md        ← 三级：issues 列表
knowledge/<project>/snippets/INDEX.md      ← 三级：snippets 列表
knowledge/<project>/troubleshooting/INDEX.md ← 三级：troubleshooting 列表
```

### b. 更新步骤

1. 读取变更文件的 frontmatter（仅 frontmatter，无需读取全文）
2. 若文件缺少 frontmatter，先按「0x01 Frontmatter 字段」补全
3. 更新对应 INDEX.md 中该文件的条目（标签、摘要、日期）
4. 向上逐级更新

> 全量重建：仅在明确要求时，读取目标目录下所有 `.md` 的 frontmatter（排除 `INDEX.md`），按更新时间倒序重新生成 INDEX.md，再向上逐级更新。

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
| Issues | [issues/](./issues/INDEX.md) | N 篇 | ... |
| 代码片段 | [snippets/](./snippets/INDEX.md) | N 篇 | ... |
```

**一级**（`knowledge/INDEX.md`）：

```markdown
| 项目 | 路径 | 数量 | 说明 |
|------|------|------|------|
| 通用知识 | [_shared/](./_shared/INDEX.md) | N 篇 | ... |
```

数量统计口径：仅统计当前可见性路径内的文件数（public 统计 public，private 统计 private），不跨域合并。

### d. 示例

```markdown
---
title: 统一查询字段映射
tags: [bkmonitor, unify-query]
description: 记录统一查询字段到数据源字段的映射关系与注意事项
created: 2026-02-10
updated: 2026-02-12
---
```
