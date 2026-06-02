---
name: knowledge-mgr
description: >
  管理工作区知识对象的检索与全生命周期操作，路径涉及 `knowledge/`，知识对象包括 issue（需求）、plan（方案 / 计划）、snippet（代码片段）和 troubleshooting（排障经验）。
  当用户询问事项进展、最近做了什么、周报 / 日报 / 总结素材，或者问题依赖历史结论、过往决策时，应优先使用本 skill。
  当用户要求将结论沉淀到知识对象体系，或者要求检索、创建、修改、归档、迁移知识对象时，应使用本 skill 执行相关操作。
  外部资料调研、纯代码实现 & 调试 & 测试等无需落地知识对象的行为不属于本 skill 场景。
---

# knowledge-mgr — 知识管理

管理工作区知识对象的检索与全生命周期操作。

## 0x00 术语介绍

知识对象：issue、plan、snippet、troubleshooting 的统称。


## 0x01 索引模型

工作区知识索引采用三级结构：

| 层级 | 路径                                        | 职责          |
|----|-------------------------------------------|-------------|
| 一级 | `knowledge/INDEX.md`                      | 项目知识概览与最近更新 |
| 二级 | `knowledge/<project>/INDEX.md`            | 项目内分类概览     |
| 三级 | `knowledge/<project>/<category>/INDEX.md` | 具体对象列表      |


知识对象脱敏隔离（`visibility`）：
* 【默认】【公开】`public`：所有知识对象都存放在 `knowledge/` 下，公开可见。
* 【私有】`private`：涉及个人隐私或敏感信息的知识对象存放在 `private/knowledge/` 下，不通过 Git 同步。
* public / private 分域维护，不跨域合并计数与索引。


## 0x02 对象模型

### a. 分类索引

所有知识对象均归属于项目，存放在 `knowledge/<project>/` 下：

| 对象              | 位置                                    | 逻辑单元           | 说明            |
|-----------------|---------------------------------------|----------------|---------------|
| issue           | `issues/<YYYY-MM-DD-title>/README.md` | issue 目录 *[1]* | 需求定义入口        |
| plan            | `issues/<YYYY-MM-DD-title>/PLAN.md`   | 隶属 issue 目录    | 方案、调研、进展与验收记录 |
| snippet         | `snippets/<title>.md`                 | 单文件            | 代码片段类知识对象     |
| troubleshooting | `troubleshooting/<title>.md`          | 单文件            | 排障经验类知识对象     |

* *[1] issue 是目录级逻辑单元，`README.md + PLAN.md = 1` 个知识对象，plan 不单独入索引，仅由 issue 条目代表整个 issue 目录。*

### b. 知识对象规范

#### Frontmatter 规范

知识对象必须包含 frontmatter，字段信息如下：

| 字段          | 必填 | 适用对象    | 说明                  |
|-------------|----|---------|---------------------|
| title       | 是  | 全部      | 文档标题                |
| tags        | 是  | 全部      | 标签数组，如 `[k8s, ops]` |
| description | 是  | 全部      | 一句话摘要               |
| language    | 否  | snippet | 代码语言                |
| issue       | 否  | plan    | 关联 issue 路径         |
| created     | 是  | 全部      | 创建日期，`YYYY-MM-DD`   |
| updated     | 是  | 全部      | 最后更新日期，`YYYY-MM-DD` |

#### 内容规范

**【CRITICAL（必须执行，不可协商）】** 确认知识对象分类，读取对应规范。
* 禁止全量阅读所有分类的规范，必须先确认分类再读对应规范，避免信息过载与混淆。
* 只在编辑、创建或评审知识对象时才需要阅读规范，单纯检索、引用、索引操作不需要阅读规范。

| 知识对象分类          | 内容规范                                                             | 样例                                  |
|-----------------|------------------------------------------------------------------|-------------------------------------|
| issue           | [Issue Writing](references/issue-writing.md)                     |                                     |
| plan            | [Plan Writing](references/plan-writing.md)                       | [方案样例](references/plan-example.md) |
| snippet         | [Snippet Writing](references/snippet-writing.md)                 |                                     |
| troubleshooting | [Troubleshooting Writing](references/troubleshooting-writing.md) |                                     |

## 0x02 场景与操作指南

### a. 检索

1）适用场景：

- 项目、进度相关问题依赖历史知识对象。
- 编码、方案设计或排障过程中，需要参考已有知识对象补充背景信息。

2）指南：[Retrieval Guide](references/retrieval.md)

### b. 操作知识对象

1）适用场景：

- 更新、归档、迁移或删除知识对象。
- 维护索引、修复链接或重建分类概览。

2）指南：
* [Operations Guide](references/operations.md)
* [Index Maintenance Guide](references/index-maintenance.md)

### c. 创建知识对象

1）适用场景：新知识沉淀到知识对象体系的场景。

2）指南：

* [Templates Guide](references/templates.md)
* [Operations Guide](references/operations.md)（仅创建流程）
