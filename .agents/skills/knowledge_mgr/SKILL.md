---
name: knowledge-mgr
title: knowledge_mgr — 知识管理
description: 创建、更新、归档、迁移、删除和索引知识对象（issue、plan、snippet、troubleshooting）。当用户想要创建任务/issue、编写计划/实施方案、记录代码片段或排障经验、修改/更新已有知识文档、归档收件箱文档、在 public/private 之间迁移知识、删除知识文档或更新知识索引时使用。
---

# knowledge_mgr — 知识管理

管理四类知识对象的全生命周期：issue / plan / snippet / troubleshooting。

所有操作支持 `visibility: public | private`，private 对象路径前缀为 `private/`，默认为 `public`。

**核心规则：任何对知识文件的变更（创建、更新、归档、迁移、删除）都必须执行「0x03 后置检查」。**

## 0x01 对象与位置

所有知识对象均归属于项目，存放在 `knowledge/<project>/` 下：

| 对象 | 位置 | 命名规则 | 模板 |
|------|------|----------|------|
| issue | `issues/<YYYY-MM-DD-title>/README.md` | 目录名：小写英文短横线 | Issue（需求）模板 |
| plan | `issues/<YYYY-MM-DD-title>/PLAN.md` | 同 issue 目录 | Plan（计划/实施方案，含进展记录）模板 |
| snippet | `snippets/<title>.md` | 文件名：小写英文短横线 | Snippet（代码片段）模板 |
| troubleshooting | `troubleshooting/<title>.md` | 文件名：小写英文短横线 | Troubleshooting（排障经验）模板 |

> 模板详见 [templates.md](templates.md)。创建文档时必须先阅读模板获取完整结构，并遵循 `.cursor/rules/markdown.mdc` 规范。

命名规则补充：

- 仅使用小写字母、数字与短横线，禁止空格与下划线
- 中文标题需转写为英文短语（必要时用拼音），确保可读且稳定
- 避免无意义缩写，优先表达问题域或功能点

所有知识文件必须包含以下 frontmatter 字段：

| 字段 | 必填 | 说明 |
|------|------|------|
| title | 是 | 文档标题 |
| tags | 是 | 标签数组，如 `[k8s, ops]` |
| description | 是 | 一句话摘要 |
| language | 否 | 仅 snippet，代码语言 |
| issue | 否 | 仅 plan，关联 issue 路径 |
| created | 是 | 创建日期，`YYYY-MM-DD` |
| updated | 是 | 最后更新日期，`YYYY-MM-DD` |

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

### d. 迁移（可见性变更）

在 `public` 与 `private` 之间迁移知识对象（本质是源侧删除 + 目标侧创建）。典型场景：内容脱敏后公开，或发现含敏感信息需转为私有。

1. 确认源文件存在，目标路径无同名文件（若冲突需用户确认）
2. 移动文件/目录到目标可见性路径（issue 须整目录迁移）
3. 执行 0x03 后置检查（源侧 + 目标侧均需检查）

### e. 删除

永久移除知识对象。

1. 确认删除目标（文件或目录）
2. 删除文件/目录
3. 执行 0x03 后置检查

## 0x03 后置检查

**任何知识文件变更后，逐项执行：**

1. **Frontmatter 维护**：确保 `updated` 为当天日期，`tags` 与内容一致
2. **目标侧索引更新**：从变更文件的**当前位置**向上逐级更新索引（参照「0x04 索引体系」）
3. **源侧索引清理**（仅迁移/删除）：从文件的**原位置**向上逐级移除旧条目并更新数量
4. **一致性自检**：
   - 索引中的标签、摘要、日期与文件 frontmatter 一致
   - 各级索引的数量与下级实际条目数一致
   - 所有索引中的相对路径链接指向实际存在的文件

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
3. **若对应层级的 INDEX.md 不存在，按 0x04.c 模板新建**
4. 更新对应 INDEX.md 中该文件的条目（标签、摘要、日期）
5. 向上逐级更新（每级同样执行 3~4 步，确保 INDEX.md 存在再更新）

> 全量重建：仅在明确要求时，读取目标目录下所有 `.md` 的 frontmatter（排除 `INDEX.md`），按更新时间倒序重新生成 INDEX.md，再向上逐级更新。

### c. 索引格式与约定

若对应层级的 INDEX.md 不存在，按以下模板新建。

**三级**（`knowledge/<project>/<category>/INDEX.md`）：

`<category>` 对应 `issues`、`snippets`、`troubleshooting` 等对象分类目录。

```markdown
# <project> <Category> 索引

| 文件 | 标签 | 摘要 | 更新日期 |
|------|------|------|---------|
| [标题](./<文件或目录>/README.md) | `tag1` `tag2` | 一句话摘要 | YYYY-MM-DD |
```

> issue 的附属文件（PLAN.md）不单独列出，仅以 issue（README.md）为条目代表整个 issue 目录。

**二级**（`knowledge/<project>/INDEX.md`）：

```markdown
# <project> 知识库

> 项目一句话描述

## 索引

| 分类 | 路径 | 数量 | 说明 |
|------|------|------|------|
| Issues | [issues/](./issues/INDEX.md) | N 篇 | ... |
| 代码片段 | [snippets/](./snippets/INDEX.md) | N 篇 | ... |
```

> blockquote 描述取自 `repos.json` 的 `description` 字段，若无则手动填写。

**一级**（`knowledge/INDEX.md`）：

```markdown
# 知识库索引

> 最后更新：YYYY-MM-DD

## 项目知识

| 项目 | 路径 | 数量 | 说明 |
|------|------|------|------|
| 通用知识 | [_shared/](./_shared/INDEX.md) | N 篇 | ... |

## 最近更新

- YYYY-MM-DD：<动作> [<标题>](<相对路径>) <补充说明>
```

**数量统计**：按逻辑单元计数——issue + 附属文件（PLAN）合计 1 篇，snippet / troubleshooting 每文件 1 篇。仅统计当前可见性路径内的数量，不跨域合并。

**最近更新**：保留最近 5 条。动作词：`新增` / `更新` / `归档` / `迁移` / `删除`。迁移注明方向如 `（private → public）`，删除操作无需链接。

### d. 示例

Frontmatter 示例：

```markdown
---
title: 统一查询字段映射
tags: [bkmonitor, unify-query]
description: 记录统一查询字段到数据源字段的映射关系与注意事项
created: 2026-02-10
updated: 2026-02-12
---
```

## 0x05 知识管理规则

以下规则由 `AGENTS.md` 引用为强制约束。

### a. RULE-KNOWLEDGE-002 — 知识检索优先级

回答项目问题或执行项目任务时，按以下优先级检索并采信：

1. 会话上下文
2. 任务上下文 → `knowledge/<project>/issues/<YYYY-MM-DD-title>/`
3. 项目知识库 → `knowledge/<project>/` + `private/knowledge/<project>/`（含 issues / snippets / troubleshooting）
4. 项目自身规范 → `<local_path>/AGENTS.md`、`<local_path>/.cursor/rules/`
5. 项目源码 → `<local_path>`（仅 1–4 未命中时）
6. 通用知识 → `knowledge/_shared/` + `private/knowledge/_shared/`
7. 工作区全局 → `AGENTS.md`、`.cursor/rules/`、`.agents/skills/`、`.cursor/skills/`

### b. RULE-ISSUE-001 — Issue 目录结构

- Issue 目录只使用 `README.md` 与 `PLAN.md` 两个文件。
- 任务进展统一写回 `PLAN.md`，不创建 `PROGRESS.md`。

### c. RULE-ISSUE-002 — 迭代交付写回

基于 issue 的迭代在出现实质变更（代码、文档或配置修改）后，交付前必须主动询问是否同步 `PLAN.md`。

- 固定句式：`是否需要我将本轮方案细节并入 0x02 方案设计，并更新 0x05 实施进展表？`
- 若用户拒绝可跳过，但下一轮仍需再次询问。

### d. RULE-ISSUE-003 — Issue 文档职责分离

1. `README.md` 只记录需求定义与方法论，不记录调研细节、对比表、语法样例结论。
2. `PLAN.md` 承载调研结论、对比分析、实现路径、验收与进展。
3. `README.md` 中允许出现"调研对象列表"，但不得展开为结论性内容。
4. 若发现 `README.md` 混入调研细节，必须先回收至 `PLAN.md` 再继续。

### e. RULE-ISSUE-004 — PLAN 迭代模式

`PLAN.md` 的迭代必须采用"方案主干融合 + 进展表格化"模式，禁止仅以补丁式追加替代主干更新。

1. 结论性变更并入 `0x02 方案设计`（或对应主设计章节），保证只看主干也能获得当前有效方案。
2. 实施进展记录在统一表格中，表头：`时间`、`结论调整概要`、`改动`。
3. 表格单元内用 `<br />` 或 `[1]`、`[2]` 角标换行，禁止松散段落。
4. 版本锚点只记录 `分支` 与 `PR`。
5. 每次写回后同步 frontmatter `updated` 为当日日期。

**迭代收口流程**：

1. 简短复盘：本轮做了什么、修了什么、验证了什么。
2. 按 RULE-ISSUE-002 主动询问用户。
3. 用户确认后，将结论并入方案主干，进展写入表格，同步 `updated` 日期。

> 若用户明确表示"本轮不更新 PLAN"，需尊重并跳过；但下一轮迭代仍需再次主动询问。
