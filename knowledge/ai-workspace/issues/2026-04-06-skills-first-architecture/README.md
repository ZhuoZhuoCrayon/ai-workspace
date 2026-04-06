---
title: Skills-First 架构演进
tags: [ai-workspace, skills, architecture, open-source]
description: 将工作区规范体系从 AGENTS.md 中心化模式演进为 Skills-First 分布式模式，并面向开源社区输出方法论
created: 2026-04-06
updated: 2026-04-06
---

# Skills-First 架构演进

## 0x01 背景

### a. Why

当前工作区的行为规范分散在三层：

- `AGENTS.md`：强制规则 + 导航入口
- `.cursor/rules/*.mdc`：专题规则（Markdown、Git、PR Review 等）
- `.agents/skills/`：任务型技能（knowledge_mgr、project_mgr 等）

实际使用中，模型在记录"确保不再犯错"的规则时，倾向于堆积到 `AGENTS.md`，而非写入对应方向的 skill 或 rule。这导致 `AGENTS.md` 逐渐膨胀，偏离"导航文件"的定位。

此外，工作区已积累了一套可复用的方法论（知识管理、项目管理、PR Review 等），具备作为标准化 skills 输出到开源社区的条件。

### b. 目标

1. **治理规则落地**：建立"规则写入对应 skill/rule，AGENTS.md 只做导航"的硬约束
2. **Rules → Skills 演进路径**：当 rule 达到一定规模时，提醒并引导抽象为 skill
3. **Skill 质量门禁**：每次新增或修改 skill，必须对照 skill-creator 规范审查
4. **开源就绪**：逐步将核心 skills 参数化，使其可被外部工作区直接安装使用

## 0x02 实现路线

### a. Skills 演进方向

- `knowledge_mgr`：知识管理（已存在，需参数化）
- `project_mgr`：项目管理（已存在，需参数化）
- `code_review`：由 `pr-review.mdc`（100 行，含多步骤流程）演进而来
- `apps_mgr`（后续）：管理 `apps/` 目录的安装与更新，将 apps 代码纳入 skill 的 assets 目录
- 通用工程类 skills：参考 [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) 选择性引入，做简化和本地化

### b. 约束

- AGENTS.md 仅保留"宪法层"硬规则（项目定位、工作目录、知识检索）和导航表
- `.cursor/rules/*.mdc` 保留轻量声明式规范（< 30 行），超阈值时提醒演进
- addyosmani/agent-skills 的理念可借鉴（anti-rationalization、verification gate、process-not-prose），但单个 skill 控制在 100-200 行，不照搬

## 0x03 参考

- [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)：19 个工程类 skills，覆盖 define → plan → build → verify → review → ship 全生命周期
- 工作区现有 skills 清单：`.agents/skills/` 下 13 个 skill
- skill-creator 规范：`.agents/skills/skill-creator/SKILL.md` + `~/.cursor/skills-cursor/create-skill/SKILL.md`
