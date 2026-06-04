# Templates Guide

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

## 0x01 调研与约束

## 0x02 架构设计

## 0x03 开发方案

<!-- 多模块场景下，可拆分为：
## 0x03 开发方案 —— <主题 A>
## 0x04 开发方案 —— <主题 B>
后续章节编号顺延。 -->

## 0x04 验收与验证

## 0x05 实施进展（表格）

<!-- 条目按时间倒序，最新进展在最上方。 -->


| 时间                     | 结论性进展                |
|------------------------|----------------------|
| `YYYY-MM-DD HH:00`（最新） | [a] ...<br />[b] ... |
| `YYYY-MM-DD HH:00`（更早） | [a] ...<br />[b] ... |

## 0x06 参考

## 0x07 版本锚点

<!-- 新建时用表格占位，确保后续文档更新能保持格式一致。 -->

| 状态 | 分支              | 里程碑        | PR                      |
|----|-----------------|------------|-------------------------|
| ✅  | `<branch_name>` | 里程碑 1（自定义） | [ xxx/repo #<number> ](<pr_url>) |
| 🔄 | `<branch_name>` | 里程碑 2（自定义） | [ xxx/repo #<number> ](<pr_url>) |

```

## 0x05 Article（文章）模板

```markdown
articles/<YYYY-MM-DD-title>/
├── README.md
└── images/

README.md
---
title: <标题>
tags: [<标签1>, <标签2>]
description: <一句话总结>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
---

# <标题>

## 0x01 概览

## 0x02 核心内容

## 0x03 参考
```

说明：

- `article` 使用目录结构。
- 正文固定放在 `README.md`。
- 图片、截图和其他文章内资源统一放在 `images/`。
- 索引链接指向目录下的 `README.md`。
