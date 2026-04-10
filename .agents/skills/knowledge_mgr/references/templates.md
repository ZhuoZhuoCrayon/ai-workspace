---
title: 知识对象模板
tags: [template, documentation]
description: 知识对象（issue、plan、snippet、troubleshooting）的标准文档模板
created: 2026-02-09
updated: 2026-04-10
---

# 知识对象模板

只在创建知识对象时阅读本文件。

所有知识对象使用统一的 frontmatter + 正文结构。

新增知识对象类型时，先补齐本文件模板、分类目录模板与索引约定，再回写 `SKILL.md` 的对象模型。

## 0x01 Troubleshooting（排障经验）模板

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

## 0x02 Snippet（代码片段）模板

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

## 0x03 Issue（需求）模板

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

## 0x04 Plan（计划/实施方案）模板

章节名称与编号可按任务复杂度调整，但必须同时满足以下约束：

- 至少保留一个承载当前有效方案的主干章节。
- 至少保留一个实施进展表格章节。
- 至少保留一个验收、验证或交付标准章节。
- 文档重心放在架构设计、关键约束、交付路径与验收标准，不展开具体实现代码，最多保留少量伪代码。

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

## 0x01 调研与约束

## 0x02 方案主干

## 0x03 实施步骤

## 0x04 验收与验证

## 0x05 实施进展（表格）

| 时间 | 对应设计片段 | 结论调整概要 | 改动 / 验证 |
|------|----------------|----------------|-------------|
| `YYYY-MM-DD HH:00` | [1] ...<br />[2] ... | [1] ...<br />[2] ... | [1] ...<br />[2] ... |

## 0x06 参考

## 0x07 版本锚点

- 分支：`<type>/<yymmdd>_<topic>`
- PR：`#<number>` 或 `<url>`
```
