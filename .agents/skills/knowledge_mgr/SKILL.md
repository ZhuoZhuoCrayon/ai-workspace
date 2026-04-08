---
name: knowledge-mgr
description: 管理工作区 knowledge 资产的检索与全生命周期操作。只要任务涉及继续既有 issue / PLAN、归档 inbox、修复索引或链接、核对 public / private 一致性、创建或维护 snippet / troubleshooting，或答案正确性依赖 `knowledge/` 与 `private/knowledge/` 中历史知识对象时，就应主动使用。若主对象位于外部系统、源码、注册表或外部资料，且任务不要求读写工作区 knowledge 资产，则不使用。
---

# knowledge_mgr — 知识管理

管理工作区知识对象的检索与全生命周期操作。

下文将 issue、plan、snippet、troubleshooting 统称为“知识对象”。

所有操作支持 `visibility: public | private`，private 对象路径前缀为 `private/`，默认为 `public`。

**【CRITICAL（必须执行不可协商）】任何知识资产写操作都必须执行后置检查，不要为了省步骤跳过 frontmatter、索引和链接一致性。**

## 0x00 触发与排除

### a. 四维判定

按任务结构而不是关键词判断是否触发 `knowledge_mgr`。

- `记忆需求`：答案是否依赖历史结论、过往决策或既有 issue / plan。
- `知识源需求`：是否需要检索 `knowledge/` 与 `private/knowledge/`。
- `持久化需求`：是否要把结果沉淀为知识对象。
- `治理需求`：是否要维护 frontmatter、INDEX、public / private 一致性。

满足任意 `2` 项即应触发 `knowledge_mgr`。满足 `3` 项及以上必须触发。

### b. 不属于本 skill 的场景

- 主对象位于工作区 knowledge 资产之外，且任务不要求创建、更新、迁移、删除、归档或核对 `knowledge/` / `private/knowledge/` 下资产。
- 纯代码实现、调试或测试，且结果不落 knowledge。
- 纯外部资料调研，且不写回 knowledge。

### c. 混合场景

- 主任务发生在外部系统，但同时要求将结论沉淀到 knowledge 体系，或核对 public / private 知识一致性时，`knowledge_mgr` 只负责知识资产相关部分。
- 用户没有显式说“写文档”，不等于可以跳过 `knowledge_mgr`。只要答案依赖历史知识资产，就应先检索。
- 模型“记得上次结论”，不等于可以跳过检索。只要答案依赖历史上下文，就要先核对 public / private 两侧知识。

### d. 参考文档

| 场景 | 首读参考文档 | 必要时补读 | 说明 |
|------|--------------|------------|------|
| 检索 | [retrieval.md](references/retrieval.md) | [retrieval-rules.md](references/retrieval-rules.md) | 回答项目问题、核对历史知识、补齐前置证据 |
| 操作 | [operations.md](references/operations.md) | [operation-rules.md](references/operation-rules.md)<br />[index-maintenance.md](references/index-maintenance.md) | 创建、更新、归档、迁移、删除与索引维护 |
| 创建对象 | [templates.md](references/templates.md) | [operations.md](references/operations.md) | 只在创建知识对象时读取模板与创建流程 |

不要一次性读取全部 `references/`；先读首读参考文档，再按需补读。

## 0x01 对象模型

所有知识对象均归属于项目，存放在 `knowledge/<project>/` 下：

| 对象 | 位置 | 逻辑单元 | 说明 |
|------|------|----------|------|
| issue | `issues/<YYYY-MM-DD-title>/README.md` | issue 目录 | 需求定义入口，`PLAN.md` 与其同目录 |
| plan | `issues/<YYYY-MM-DD-title>/PLAN.md` | 隶属 issue 目录 | 方案、调研、进展与验收记录 |
| snippet | `snippets/<title>.md` | 单文件 | 代码片段类知识对象 |
| troubleshooting | `troubleshooting/<title>.md` | 单文件 | 排障经验类知识对象 |

新增知识对象类型时，先扩展本节对象模型、[templates.md](references/templates.md) 与对应分类索引，再补充操作流程。

命名规则、frontmatter 字段与对象模板见 [operations.md](references/operations.md) 和 [templates.md](references/templates.md)。

## 0x02 索引模型与不变量

工作区知识索引采用三级结构：

| 层级 | 路径 | 职责 |
|------|------|------|
| 一级 | `knowledge/INDEX.md` | 项目知识概览与最近更新 |
| 二级 | `knowledge/<project>/INDEX.md` | 项目内分类概览 |
| 三级 | `knowledge/<project>/<category>/INDEX.md` | 具体对象列表 |

必须保持以下不变量：

- issue 是目录级逻辑单元，`README.md + PLAN.md = 1` 个知识对象。
- `PLAN.md` 不单独入索引，仅由 issue 条目代表整个 issue 目录。
- public / private 分域维护，不跨域合并计数与索引。
- 任意知识资产写操作都要同步 `updated` 为当日日期。
- 任意知识资产写操作都要同步索引、数量统计和相对路径链接一致性。

索引更新步骤、模板和全量重建规则见 [index-maintenance.md](references/index-maintenance.md)。

## 0x03 规则锚点

| 规则 | 入口 | 摘要 |
|------|------|------|
| `RULE-KNOWLEDGE-002` | [retrieval-rules.md](references/retrieval-rules.md) | 知识检索优先级 |
| `RULE-ISSUE-001` | [operation-rules.md](references/operation-rules.md) | Issue 目录仅含 `README.md` 与 `PLAN.md` |
| `RULE-ISSUE-002` | [operation-rules.md](references/operation-rules.md) | 迭代交付前主动询问 PLAN 写回 |
| `RULE-ISSUE-003` | [operation-rules.md](references/operation-rules.md) | Issue 文档职责分离 |
| `RULE-ISSUE-004` | [operation-rules.md](references/operation-rules.md) | PLAN 迭代采用主干实时更新 + 进展表格化 |
