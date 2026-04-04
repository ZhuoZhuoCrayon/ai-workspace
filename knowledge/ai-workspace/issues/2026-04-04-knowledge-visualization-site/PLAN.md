---
title: AI 工作区知识资产可视化页面 —— 实施方案
tags: [ai-workspace, docs, visualization, github-pages, vitepress]
issue: knowledge/ai-workspace/issues/2026-04-04-knowledge-visualization-site/README.md
description: 知识资产可视化页面的技术选型、实施计划与执行记录
created: 2026-04-04
updated: 2026-04-04
---

# AI 工作区知识资产可视化页面 —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 选型结论

### a. 候选方案

| 方案 | 优势 | 风险/不足 | 结论 |
|------|------|-----------|------|
| VitePress（Vue 3） | Markdown 阅读体验成熟；TOC/搜索/路由开箱即用；GitHub Pages 官方示例完整 | 看板定制需自定义 Vue 组件 | **v2 采用** |
| Astro + Starlight | 默认全文搜索（Pagefind）开箱；阅读体验好 | 为"文档内容站"优化，项目资产看板与注册表联动需额外适配 | 备选 |
| React + Vite（自定义页面） | 资产看板/过滤/搜索交互自由度最高 | 需自行实现 TOC、路由、标题层级、链接解析等文档阅读基础能力 | v1 已废弃 |

### b. 演进历程

**v1（React + Vite，已废弃）**：优先完成可用 MVP，但上线后暴露 9 个体验问题，其中 6 个属于文档阅读框架级缺陷（TOC、路由、标题层级、链接解析、搜索、独立页面），逐一补齐约等于自造 VitePress。

**v2（VitePress，当前方案）**：推倒重来，利用 VitePress 默认主题开箱即用地解决上述问题，并通过自定义 Vue 组件实现知识看板、标签云、日历活动图。

### c. 核心策略

1. 文档发现：通过 `knowledge/INDEX.md`（+ `private/knowledge/INDEX.md`）BFS 遍历发现文档，同时递归 `README.md` 以发现 PLAN 等子文档。
2. 项目发现：通过 `repos.json` + `private/repos.json`（兼容 `repos.yaml`）聚合项目清单。
3. 构建期生成：构建脚本复制文档到 VitePress srcDir 并清洗 frontmatter，输出 sidebar 配置、标签索引、日历数据。
4. 交互：VitePress 本地全文搜索、标签索引页、项目索引页、右侧 TOC、暗色模式。
5. 部署：GitHub Actions → GitHub Pages。

## 0x02 评估范围

- 本轮交付"可运行、可检索、可部署"的完整阅读体验。
- 暂不做账户体系、在线编辑、评论系统等扩展能力。
- 保持纯静态站点 + 构建期数据生成。

## 0x03 实施清单

| 阶段 | 任务 | 状态 |
|------|------|------|
| v1 Phase 1 | React + Vite MVP（三栏布局、搜索、部署） | 已完成（已废弃） |
| v2 Phase 1 | 删除 React 代码，初始化 VitePress 工程 | 已完成 |
| v2 Phase 1 | 重写 `generate-vitepress-config.mjs`（BFS 遍历 + frontmatter 清洗 + 文件复制） | 已完成 |
| v2 Phase 1 | 配置 VitePress：sidebar、nav、local search、outline | 已完成 |
| v2 Phase 2 | 首页看板：统计卡片、最近更新、项目分布 | 已完成 |
| v2 Phase 2 | TagCloud + 标签索引页 + 项目索引页 | 已完成 |
| v2 Phase 2 | DocMeta 组件：自动注入文档顶部标签/项目/日期 | 已完成 |
| v2 Phase 3 | ActivityCalendar：GitHub-style 365 天活动热力图 | 已完成 |
| v2 Phase 3 | 更新 CI workflow（`docs:build`、`dist` 路径） | 已完成 |
| v2 Phase 3 | 端到端验证：61 篇文档、7 个项目、103 种标签 | 已完成 |

## 0x04 风险与应对

- **私有资产缺失**：`private/` 在 GitHub Pages 构建环境不可见 → 读取失败时自动降级为公开数据。
- **INDEX.md 链接不全**：构建脚本输出未解析链接告警，不阻断构建。
- **frontmatter 损坏**：部分历史文档 frontmatter 非法 → 构建脚本清洗后复制，灾难性解析失败时回退为纯 Markdown。

## 0x05 执行记录

### a. 2026-04-04（v1：React、Vite）

- 完成选型评估并确定本期采用 React、Vite。
- 完成工程初始化、数据脚本、页面实现、部署流程。
- 已知问题：部分历史文档 frontmatter 非法，生成脚本降级处理。

### b. 2026-04-04（v2：VitePress 重构）

- 识别 v1 的 9 个体验缺陷（无 TOC、无路由、标题层级错乱、站内链接不可用等），决定推倒重来。
- 删除全部 React 代码（`src/`、React 依赖），切换为 VitePress 1.x + Vue 3。
- 重写构建脚本 `generate-vitepress-config.mjs`：
  - 沿用 INDEX.md BFS 遍历，新增 README.md 递归以发现 PLAN/PROGRESS 等子文档（55→61 篇）。
  - 新增 frontmatter 清洗与文件复制机制（解决 VitePress 对损坏 frontmatter 的严格解析问题）。
  - 输出 `sidebar.generated.json`、`meta.generated.json`、`tags.md`、`projects.md`。
- 自定义 Vue 组件：`HomeDashboard`、`TagCloud`、`ActivityCalendar`、`DocMeta`、`DocMetaLayout`。
- 更新 CI workflow：`npm run docs:build`，产物路径改为 `docs/.vitepress/dist`。
- 端到端验证：构建 2.96s / 4.8MB，全部页面 200，sidebar/TOC/搜索/标签跳转/站内链接均可用。

### c. 2026-04-04（v2：体验优化与稳定性修复）

#### 目标与问题定位

- 首页 Hero 文案（`AI 工作台知识库`）与顶部导航搜索框视觉距离过近，首屏呼吸感不足。
- 首页「最近更新 / 项目分布」两列内容起始线不齐，存在明显错位。
- Issue/Plan 页面 Mermaid 未渲染，影响方案阅读体验（例如 `knowledge/bkmonitor/issues/2026-03-03-apm-shared-datasource/PLAN.md`）。

#### 根因与关键决策

- Mermaid 根因：VitePress 实际输出容器为 `.language-mermaid`，旧逻辑仅匹配 `pre code.language-mermaid`，导致未命中替换。
- 两列错位根因：通用规则 `.panel + .panel` 作用到 grid 内第二张卡片，导致右列整体下移。
- 对齐策略：统一首页内容栅格（Hero 与 Dashboard 同一左右边界），并给两列工具栏预留等高行。

#### 变更清单（文件级）

| 文件 | 关键变更 |
|------|----------|
| `apps/knowledge-portal/docs/.vitepress/theme/index.ts` | Mermaid 渲染逻辑升级：支持 `.language-mermaid` 容器，保留旧选择器兼容；`mermaid.run` 启用 `suppressErrors`。 |
| `apps/knowledge-portal/docs/.vitepress/theme/style/custom.css` | 首页视觉体系升级：Hero 间距、背景层次、字体与按钮状态；加大 Hero 顶部留白，缓解与搜索栏距离过近问题。 |
| `apps/knowledge-portal/docs/.vitepress/theme/components/HomeDashboard.vue` | 首页卡片化重构；最近更新类型筛选；项目分布工具栏；修复 grid 内额外 margin 导致的列错位。 |
| `apps/knowledge-portal/docs/.vitepress/theme/components/ActivityCalendar.vue` | 日历视觉细化：月份标签可读性、格子 hover 反馈与边框。 |
| `apps/knowledge-portal/docs/.vitepress/theme/components/TagCloud.vue` | 标签云热度分层与 focus/hover 可访问性增强。 |
| `apps/knowledge-portal/docs/.vitepress/theme/components/IssueSwitch.vue` | Issue 内入口文案优化：`README/PLAN` → `需求概述/方案`。 |

#### 验证矩阵

| 页面 | 验证项 | 结果 |
|------|--------|------|
| `/` | Hero 与 Dashboard 左边界对齐（桌面/移动） | 通过 |
| `/` | 最近更新 / 项目分布 首行对齐 | 通过 |
| `/` | 活动日志文案与数字链接展示 | 通过 |
| `/knowledge/bkmonitor/issues/2026-03-03-apm-shared-datasource/plan.html` | Mermaid 图渲染（多图） | 通过（10/10） |
| 全站 | `npm run docs:build` | 通过 |

#### 版本锚点

- 提交：`9c525bb`
- Commit Message：`feat(knowledge-portal): polish portal UX and fix mermaid rendering`
- 推送：`main -> origin/main`（`bdcff21..9c525bb`）

#### 接手提示（给后续 Agent）

- 本地验收优先使用：`npm run docs:build` + `npm run docs:preview -- --port 4175`，避免陈旧进程导致静态资源 hash 404。
- 验证 Mermaid 时优先检查两点：页面中是否存在 `.language-mermaid`，以及是否替换为 `.vp-mermaid svg`。
- 首页布局改动需同时验收桌面与移动，尤其关注 Hero 顶部留白与两列列表起始线对齐。

### d. 2026-04-04（v2：交互补强与规则固化）

#### 本轮新增优化

- 修复 Issue 内 `需求概述 / 方案` 切换选中态：兼容 GitHub Pages `base` 路径，避免 `plan.html` 下无高亮。
- 项目入口补充仓库跳转交互：
  - 首页「项目分布」增加 Git 平台按钮（`GitHub` / `Git WOA`）。
  - `projects.md` 新增「仓库」列并输出可点击链接。
- 补齐缺失仓库描述：为 `throttled-py` 回填 description（来源：GitHub 仓库描述）。
- 修复历史 frontmatter 异常：`knowledge/bkm-skills/issues/2026-03-01-ci-helper-best-practices/README.md`。

#### 规范固化（减少重复沟通）

- 在 `AGENTS.md` 新增 `RULE-ISSUE-002`：基于 issue 的迭代在交付前必须主动询问是否同步 `PLAN.md`。
- 在 `knowledge_mgr` 新增「0x05 迭代收口（Issue 场景）」：固定提问句与写回模板（变更摘要 / 关键结论 / 验证结果 / 风险后续 / 版本锚点）。
- 在 `project_mgr` 新增「描述补齐策略」：`Git 平台描述 -> README 首段 -> 占位描述`，并允许巡检时只补齐空描述字段。

#### 验证结果

| 验证项 | 结果 |
|------|------|
| `需求概述 / 方案` 在 `plan.html` 页选中态 | 通过 |
| 首页项目分布 Git 平台跳转可见且可点击 | 通过 |
| `projects.md` 仓库列渲染 | 通过 |
| frontmatter 异常告警（`ci-helper-best-practices`） | 已消除 |
| 文档规范检查（规则文档 + PLAN） | 通过 |

## 0x06 参考

- [VitePress Deploy](https://vitepress.dev/guide/deploy)
- [VitePress Local Search](https://vitepress.dev/reference/default-theme-search)
- [VitePress Build-Time Data Loading](https://vitepress.dev/guide/data-loading)
- [VitePress Extending Default Theme](https://vitepress.dev/guide/extending-default-theme)
