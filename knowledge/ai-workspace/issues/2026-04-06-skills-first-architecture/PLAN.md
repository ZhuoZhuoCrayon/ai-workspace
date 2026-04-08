---
title: Skills-First 架构演进 —— 实施方案
tags: [ai-workspace, skills, architecture, open-source]
issue: knowledge/ai-workspace/issues/2026-04-06-skills-first-architecture/README.md
description: 工作区规范体系从 AGENTS.md 中心化向 Skills-First 分布式演进的实施方案
created: 2026-04-06
updated: 2026-04-08
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

- 单个 skill 优先控制在 100-200 行。超过 200 行时，需给出不拆分理由或拆分计划
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

### d. knowledge_mgr 过渡演进策略

当前阶段先不新增 `knowledge_search` skill，而是将“主动知识检索”收敛到 `knowledge_mgr`。

- `knowledge_mgr` 负责：触发判定、双路检索顺序、证据输出格式、知识未命中后的源码回退条件，以及工作区 knowledge 资产的全生命周期操作。
- `knowledge_mgr` 不负责：独立检索算法、召回重排、长期检索优化实验。
- `knowledge_mgr` 的 `SKILL.md` 只保留骨架级内容：触发与排除、知识对象模型、索引不变量、规则锚点。
- 具体流程按需下沉到 `references/`，当前分层为：
  - 检索入口：`retrieval.md`
  - 检索规则原文：`retrieval-rules.md`
  - 写操作入口：`operations.md`
  - 写操作规则原文：`operation-rules.md`
  - 索引维护专用：`index-maintenance.md`
  - 对象模板：`templates.md`
- `knowledge_mgr` 不显式感知其他 skills，只定义自身适用边界；是否调用其他 skill 由外层路由决定。
- 知识对象统一抽象为 `issue`、`plan`、`snippet`、`troubleshooting`，后续扩展新对象类型时，先更新对象模型、模板与分类索引，再补操作流程。
- 未来若拆出 `knowledge_search`，保持 `RULE-KNOWLEDGE-002` 编号和证据输出格式不变，避免迁移成本外溢到 `AGENTS.md` 与调用方。
- 拆分触发条件：满足任意 `3` 条即启动拆分评估。
  - `knowledge_mgr` 总长度持续超过 `200` 行，且检索相关内容超过 `35%`
  - 连续两周内，`knowledge_mgr` 变更中检索相关占比超过 `50%`
  - 出现 `3` 类以上“只检索不写入”的稳定场景
  - 检索链路需要独立能力，例如语义召回、索引构建、重排
  - 一个月内出现 `2` 次以上检索优先级或证据格式不一致问题

### e. AGENTS 与 PLAN 的治理收敛

- `AGENTS.md` 只保留全局结构性约束与导航，不重复展开 `knowledge_mgr` 的规则正文。
- 知识与 Issue 管理规则在 `AGENTS.md` 中仅指向 `knowledge_mgr/SKILL.md` 的 `0x03 规则锚点`，避免双份维护与摘要漂移。
- `PLAN.md` 必须是架构师视角的活文档：承载当前有效方案、关键约束、交付路径与验收标准，而不是实现流水账。
- `PLAN.md` 的章节编号和命名可按任务复杂度调整，但必须同时具备：
  - 方案主干章节
  - 实施进展表格章节
  - 验收、验证或交付标准章节
- 每轮写回时，先定位受影响的设计片段并更新主干，再将实施进展写入表格；不将固定章节号写死在规则中。

## 0x03 实施步骤

### a. 治理规则落地（已完成）

- [x] 创建 Issue 记录需求
- [x] AGENTS.md 添加 RULE-GOVERN-001/002/003
- [x] 创建 PLAN

### b. knowledge_mgr 检索能力收敛（P0）

- [x] 按 `skill-creator` 规范审查 `knowledge_mgr` 的 frontmatter、触发描述和结构边界
- [x] 在 `knowledge_mgr` 中补充“触发判定”与“检索契约”，让知识目录检索行为和知识管理行为默认主动使用该 skill
- [x] 将 `SKILL.md` 收敛为骨架入口，并按检索、写操作、索引维护、模板拆分 `references/`
- [x] 将索引维护从默认写操作链路中拆出，新增 `index-maintenance.md`
- [x] 在 `AGENTS.md` 中回收知识与 Issue 管理规则的重复列举，仅保留到 `knowledge_mgr` `0x03` 的导航
- [x] 在 `general.mdc` 中修正 skill 入口路径，并补充 `knowledge_mgr` 入口提示
- [x] 在 `markdown.mdc` 中补充表格脚注与角标规则，支撑 progressive disclosure 文档写法
- [x] 建立并扩展回归用例到 `9` 条，覆盖应触发、不应触发、知识检索导航、PLAN 写回、索引清理、证据冲突升级、索引维护拆分

### c. PR Review 演进为 code_review skill（P0）

- [ ] 基于 `pr-review.mdc` 内容创建 `.agents/skills/code_review/SKILL.md`
- [ ] 按 skill-creator 规范审查（frontmatter、progressive disclosure、< 200 行）
- [ ] 删除 `pr-review.mdc`，更新 AGENTS.md 快速入口表

### d. Markdown 规范演进为 doc_style skill（P1）

- [ ] 基于 `markdown.mdc` 内容创建 `.agents/skills/doc_style/SKILL.md`
- [ ] 删除 `markdown.mdc`，更新 AGENTS.md 快速入口表

### e. 通用规范与 Git 规范演进为 skills（P2）

- [ ] `git.mdc` → `.agents/skills/git_workflow/SKILL.md`
- [ ] `general.mdc` → 拆分融入各场景 skill 或创建 bootstrap skill
- [ ] 删除原 `.mdc` 文件

### f. 语言开发规范演进为 skills（P3）

- [ ] 合并或独立创建语言开发 skills（go-dev、python-type-annotations）
- [ ] 删除原 `.mdc` 文件

### g. apps_mgr skill

- [ ] 设计 apps 目录管理流程（安装、更新、assets 同步）
- [ ] 创建 `.agents/skills/apps_mgr/SKILL.md`
- [ ] 实现"初始化"命令：`make init` + apps 安装

### h. 开源参数化

- [ ] knowledge_mgr：配置化知识目录结构
- [ ] project_mgr：抽象注册表格式
- [ ] 编写 README 和安装指南

### i. 引入工程类 skills

- [ ] 从 addyosmani/agent-skills 选择 3-5 个高价值 skill
- [ ] 简化到 100-200 行并本地化
- [ ] 集成到工作区 skills 体系

## 0x04 验收与验证

- AGENTS.md 行数不增长（仅做导航）
- 新的行为规范写入对应 skill，禁止写入 AGENTS.md
- 每个 skill 通过 skill-creator 规范审查
- 知识目录检索行为与知识管理行为默认主动走 `knowledge_mgr`
- `knowledge_mgr` 保持契约层职责，不扩展为独立检索引擎
- `knowledge_mgr/SKILL.md` 保持骨架入口定位；具体流程按需从 `references/` 读取
- `AGENTS.md` 对知识与 Issue 管理仅保留导航，不重复维护规则摘要
- `PLAN.md` 写回遵循“主干实时更新 + 进展表格化”，不绑定固定章节编号
- 回归用例当前沉淀 `9` 条；扩展到 `12` 条后至少 `11 / 12` 通过
- 最近一次评测结果与报告路径可追溯，避免阈值与实际通过率漂移
- `.cursor/rules/` 最终清空（全部迁入 skills）

## 0x05 实施进展（表格）

| 时间 | 对应设计片段 | 结论调整概要 | 改动 / 验证 |
|------|----------------|----------------|-------------|
| 2026-04-06 | `0x02.a`、`0x02.b`、`0x03.a` | [1] 确立两层架构（宪法层 + Skills 层），rules 为过渡态<br />[2] 评估 6 条现有 rules，全部规划演进时间线<br />[3] skill 分类明确：工作区治理（可输出）/ 工程实践（可输出）/ 场景 skills（按需内置） | [1] 创建 Issue + PLAN<br />[2] AGENTS.md 添加 RULE-GOVERN-001/002/003<br />[3] 更新 PLAN：rules 全部规划演进，skill 分类修正 |
| 2026-04-08 | `0x02.d`、`0x04` | [1] 明确当前阶段不新建 `knowledge_search`，先将主动知识检索收敛到 `knowledge_mgr`<br />[2] 补充拆分触发条件与契约边界，避免 `knowledge_mgr` 膨胀为大杂烩<br />[3] 将“默认主动使用 knowledge_mgr”纳入验收与回归要求<br />[4] 通过轻量评测发现 iWiki 场景仍可能被过度吸入 `knowledge_mgr`，因此将竞争排除升级为短路规则 | [1] 设计 `knowledge_mgr` 触发判定、检索契约与兼容声明<br />[2] 建立首批 `6` 条回归用例，并将通过标准改为离散阈值<br />[3] 补跑 `3` 组 with-skill / baseline 评测，并修正 iWiki 场景的默认不触发语义 |
| 2026-04-08 | `0x02.d`、`0x02.e`、`0x03.b`、`0x04` | [1] `knowledge_mgr` 收敛为骨架入口 + `references/` 分层，默认读取负担明显下降<br />[2] `AGENTS.md` 回到纯导航，只指向 `knowledge_mgr` 的规则锚点，避免重复维护规则摘要<br />[3] `PLAN` 写回规则改为“方案主干实时更新 + 进展表格化”，不再绑定固定章节号<br />[4] 知识对象统一抽象与索引维护拆分到位，为后续新增对象类型保留扩展路径 | [1] 将 `SKILL.md` 收敛到触发、对象模型、索引不变量、规则锚点四类骨架内容<br />[2] 新增 `index-maintenance.md`，并将模板迁移到 `references/templates.md`<br />[3] 更新 `operation-rules.md`、`templates.md` 与 `evals.json`，把写回语义改成“更新受影响的方案主干片段 + 记录实施进展”<br />[4] 更新 `AGENTS.md`、`general.mdc`、`markdown.mdc`，并通过 `markdownlint-cli2`、`check-doc-style`、`lint-md` 与 JSON 校验 |

## 0x06 参考

- [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)
- [GeminiLight/MindOS](https://github.com/GeminiLight/MindOS)
- [skill-creator 规范](./../../../../.agents/skills/skill-creator/SKILL.md)
