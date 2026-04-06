---
title: Skills-First 架构演进 —— 实施方案
tags: [ai-workspace, skills, architecture, open-source]
issue: knowledge/ai-workspace/issues/2026-04-06-skills-first-architecture/README.md
description: 工作区规范体系从 AGENTS.md 中心化向 Skills-First 分布式演进的实施方案
created: 2026-04-06
updated: 2026-04-06
---

# Skills-First 架构演进 —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 调研

### a. 现有 Rules 演进评估

**核心结论**：`.cursor/rules/*.mdc` 是 Cursor 特有格式，不可迁移到 Claude Code、Codex、Gemini CLI 等其他 agent 环境。Skills 是 agent-agnostic 的 Markdown 工作流，是规范的通用包装格式。因此所有 rules 最终都应演进为 skills，rules 只是过渡态。

| Rule 文件 | 行数 | 演进方向 | 优先级 |
|-----------|------|---------|--------|
| `pr-review.mdc` | 100 | → `code_review` skill | P0 |
| `markdown.mdc` | 88 | → `doc_style` skill（文档写作规范） | P1 |
| `general.mdc` | 27 | → 融入工作区 bootstrap skill 或拆分到各场景 skill | P2 |
| `git.mdc` | 21 | → `git_workflow` skill | P2 |
| `go-dev.mdc` | 15 | → 融入语言开发 skill（可与同类合并） | P3 |
| `python-type-annotations.mdc` | 22 | → 融入语言开发 skill（可与同类合并） | P3 |

### b. addyosmani/agent-skills 可借鉴模式

值得采纳：

- **Anti-rationalization table**：列出模型常见"跳过步骤"的借口及反驳，防止偷工减料
- **Verification gate**：每个 skill 以证据要求收尾，"seems right" 不算完成
- **Process-not-prose**：skill 是流程而非文档，有步骤、检查点和退出条件

需本地化调整：

- 单个 skill 控制在 100-200 行（原仓库动辄 500+ 行，token 开销过大）
- 去除英文工程文化特定内容，保留结构化流程骨架
- 与工作区现有 skill-creator 规范对齐

## 0x02 方案设计

### a. 两层架构（目标态）

```text
┌─────────────────────────────────────────────┐
│  AGENTS.md（宪法层）                          │
│  全局结构性约束 + 导航入口                     │
│  RULE-LOCATE / RULE-WD / RULE-KNOWLEDGE      │
│  RULE-GOVERN（规则治理）                      │
└──────────────────┬──────────────────────────┘
                   │ 按需加载
                   ▼
          ┌──────────────────┐
          │ Skills 层         │
          │ .agents/skills/   │
          │ agent-agnostic    │
          │ 可迁移、可开源     │
          └──────────────────┘
```

过渡期间 `.cursor/rules/*.mdc` 仍存在，但每条 rule 都有明确的演进目标和优先级，最终全部迁入 skills。

### b. Skill 分类

| 类别 | 定位 | 示例 | 开源属性 |
|------|------|------|---------|
| 工作区治理 | 知识/项目/应用管理 | knowledge_mgr, project_mgr, apps_mgr | 可输出（需参数化） |
| 工程实践 | 开发/测试/发布流程 | code_review, doc_style, git_workflow | 可输出 |
| 场景 skills | 按需内置的工具/平台集成 | docx, xlsx, pptx, pdf, iwiki-doc, bk-ci-helper, bk-rpc-inspection, mcp-builder | 按需内置，不对外 |

### c. 开源输出策略

核心可输出 skills（需参数化）：

- `knowledge_mgr`：去除 repos.json 硬编码，改为配置化的知识目录结构
- `project_mgr`：抽象注册表格式，不绑定 repos.json schema
- `code_review`：从 pr-review.mdc 演进，通用化 PR review 流程
- `doc_style`：从 markdown.mdc 演进，通用文档写作规范
- `git_workflow`：从 git.mdc 演进，Git 工作流规范

场景 skills（按需内置，不纳入开源输出）：

- docx / xlsx / pptx / pdf：Office 文档处理
- iwiki-doc / iwiki_sync：内部 Wiki 集成
- bk-ci-helper / bk-rpc-inspection / bk-mcp-builder / bk-data-fetcher：蓝鲸平台专项

## 0x03 实施步骤

### a. 治理规则落地（已完成）

- [x] 创建 Issue 记录需求
- [x] AGENTS.md 添加 RULE-GOVERN-001/002/003
- [x] 创建 PLAN

### b. PR Review 演进为 code_review skill（P0）

- [ ] 基于 `pr-review.mdc` 内容创建 `.agents/skills/code_review/SKILL.md`
- [ ] 按 skill-creator 规范审查（frontmatter、progressive disclosure、< 200 行）
- [ ] 删除 `pr-review.mdc`，更新 AGENTS.md 快速入口表

### c. Markdown 规范演进为 doc_style skill（P1）

- [ ] 基于 `markdown.mdc` 内容创建 `.agents/skills/doc_style/SKILL.md`
- [ ] 删除 `markdown.mdc`，更新 AGENTS.md 快速入口表

### d. 通用规范与 Git 规范演进为 skills（P2）

- [ ] `git.mdc` → `.agents/skills/git_workflow/SKILL.md`
- [ ] `general.mdc` → 拆分融入各场景 skill 或创建 bootstrap skill
- [ ] 删除原 `.mdc` 文件

### e. 语言开发规范演进为 skills（P3）

- [ ] 合并或独立创建语言开发 skills（go-dev、python-type-annotations）
- [ ] 删除原 `.mdc` 文件

### f. apps_mgr skill

- [ ] 设计 apps 目录管理流程（安装、更新、assets 同步）
- [ ] 创建 `.agents/skills/apps_mgr/SKILL.md`
- [ ] 实现"初始化"命令：`make init` + apps 安装

### g. 开源参数化

- [ ] knowledge_mgr：配置化知识目录结构
- [ ] project_mgr：抽象注册表格式
- [ ] 编写 README 和安装指南

### h. 引入工程类 skills

- [ ] 从 addyosmani/agent-skills 选择 3-5 个高价值 skill
- [ ] 简化到 100-200 行并本地化
- [ ] 集成到工作区 skills 体系

## 0x04 验收与验证

- AGENTS.md 行数不增长（仅做导航）
- 新的行为规范写入对应 skill，禁止写入 AGENTS.md
- 每个 skill 通过 skill-creator 规范审查
- `.cursor/rules/` 最终清空（全部迁入 skills）

## 0x05 实施进展（表格）

| 时间 | 结论调整概要 | 改动 |
|------|------|------|
| 2026-04-06 | [1] 确立两层架构（宪法层 + Skills 层），rules 为过渡态<br />[2] 评估 6 条现有 rules，全部规划演进时间线<br />[3] skill 分类明确：工作区治理（可输出）/ 工程实践（可输出）/ 场景 skills（按需内置） | [1] 创建 Issue + PLAN<br />[2] AGENTS.md 添加 RULE-GOVERN-001/002/003<br />[3] 更新 PLAN：rules 全部规划演进，skill 分类修正 |

## 0x06 参考

- [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)
- [skill-creator 规范](./../../../.agents/skills/skill-creator/SKILL.md)
- [create-skill 规范](~/.cursor/skills-cursor/create-skill/SKILL.md)
