---
title: AI 工作区知识资产可视化页面 —— 实施方案
tags: [ai-workspace, docs, visualization, github-pages, react]
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
| VitePress（Vue 3） | Markdown 阅读体验成熟；本地搜索能力完善；GitHub Pages 官方示例完整 | 面向“文档站”范式更强，知识资产看板与复合检索定制成本中等 | 备选 |
| Astro + Starlight | 默认全文搜索（Pagefind）开箱；阅读体验好 | 为“文档内容站”优化，项目资产看板与注册表联动需额外适配 | 备选 |
| React + Vite（自定义页面） | 资产看板/过滤/搜索交互自由度最高；可严格落实 INDEX 驱动发现与 repos 注册表发现 | 需要自行打磨阅读体验和搜索细节 | **本期采用** |

### b. 采用策略

本期采用 `React + Vite`，优先完成可用 MVP：

1. 文档发现：仅通过 `knowledge/INDEX.md`（及可用时 `private/knowledge/INDEX.md`）递归遍历链接发现文档。
2. 项目发现：通过 `repos.json` + `private/repos.json`（并兼容 `repos.yaml`）聚合项目清单。
3. 交互：支持关键字检索、项目过滤、文档列表与 Markdown 阅读。
4. 部署：通过 GitHub Actions 持续部署到 GitHub Pages。

## 0x02 评估范围（精简）

- 本轮只交付“可运行、可检索、可部署”的最小闭环。
- 暂不做账户体系、在线编辑、评论系统等扩展能力。
- 暂不引入复杂后端，保持纯静态站点 + 构建期数据生成。

## 0x03 实施清单

| 阶段 | 任务 | 状态 |
|------|------|:--:|
| Phase 1 | 新建 `apps/knowledge-portal`（React + Vite + TS） | 已完成 |
| Phase 1 | 实现 `INDEX.md` 递归遍历与文档元数据构建脚本 | 已完成 |
| Phase 1 | 实现 `repos.json`/`private/repos.json`（含 yaml 兼容）项目发现器 | 已完成 |
| Phase 1 | 完成首页资产看板 + 搜索 + 阅读三栏布局 | 已完成 |
| Phase 1 | 新增 GitHub Pages 部署工作流 | 已完成 |
| Phase 1 | 本地构建验证与问题收敛 | 已完成 |

## 0x04 风险与应对

- 风险：`private/` 在 GitHub Pages 构建环境不可见，导致私有资产缺失。
- 应对：读取失败时自动降级为公开数据，不阻断构建。

- 风险：`INDEX.md` 书写不规范导致链接解析不全。
- 应对：构建脚本输出未解析链接统计，并在控制台显式提示。

## 0x05 执行记录

### a. 2026-04-04

- 完成选型评估并确定本期采用 `React + Vite`。
- 完成工程初始化：`apps/knowledge-portal`。
- 完成数据层脚本：`scripts/generate-knowledge-data.mjs`。
  - 文档来源：`knowledge/INDEX.md` + `private/knowledge/INDEX.md` 递归遍历链接。
  - 项目来源：`repos.json` + `private/repos.json`，并兼容 `repos.yaml`。
- 完成页面实现：资产概览、关键字搜索、项目过滤、Markdown 阅读。
- 完成部署流程：新增 `.github/workflows/knowledge-portal-pages.yml`。
- 完成本地验证：`npm run build`、`npm run lint` 通过。
- 文档校验说明：工作区存在历史存量告警，本轮对变更文档执行三轨检查通过。
- 已知问题：部分历史文档 frontmatter 非法，生成脚本已降级为“按纯 Markdown 继续处理并告警”。

## 0x06 参考（官方）

- VitePress Deploy（GitHub Pages）：https://vitepress.dev/guide/deploy
- VitePress Local Search：https://vitepress.dev/reference/default-theme-search
- VitePress Build-Time Data Loading：https://vitepress.dev/guide/data-loading
- Astro Deploy（GitHub Pages）：https://docs.astro.build/en/guides/deploy/github/
- Starlight Site Search：https://starlight.astro.build/guides/site-search/
- Docusaurus Search：https://docusaurus.io/docs/search
