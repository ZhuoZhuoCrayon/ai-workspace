---
title: 文档规范检查工具替代调研 —— 实施方案
tags: [ai-workspace, docs, tooling, lint]
issue: knowledge/ai-workspace/issues/2026-04-04-doc-style-tooling-research/README.md
description: 基于 lint-md 的替代方案调研与 PoC 执行记录
created: 2026-04-04
updated: 2026-04-04
---

# 文档规范检查工具替代调研 —— 实施方案

> 基于 [README.md](./README.md) 制定。

## 0x01 评估范围

### a. 基线与边界

本次只评估“替代 `scripts/check_doc_style.py`”所需的核心能力：

- Markdown 结构规则（标题层级、代码块语言、尾换行）
- 文案规则（中英文混排、标点）
- 仓库特有规则（文件名、`## 0x01` / `### a.`、`.mdc` frontmatter）

## 0x02 覆盖矩阵

| 现有规则 | lint-md | 结论 |
|------|------|------|
| CJK / Latin 间距 | 原生规则 `space-around-alphabet` | 可替代 |
| 中文 / 数字间距 | 原生规则 `space-around-number` | 可替代 |
| 代码块语言必填 | 原生规则 `no-empty-code-lang` | 可替代 |
| 省略号规范 | 原生规则 `use-standard-ellipsis` | 可替代（注意默认允许 `...`） |
| 标题尾标点规范 | 原生规则 `correct-title-trailing-punctuation` | 可替代 |
| Markdown 结构（标题层级、尾换行） | 非核心覆盖（更偏中文文案规则） | 建议继续由现有脚本 / markdownlint 覆盖 |
| `.mdc` frontmatter 字段校验 | 无内建 schema 校验 | 需保留定制 |
| 文件名规则、`## 0x01` / `### a.` | 无内建规则 | 需保留定制 |

## 0x03 结论与建议

### a. 结论

`lint-md` 是目前最贴近 [document-style-guide](https://github.com/ruanyf/document-style-guide) 的现成检查工具，可替代一大块中文文案规范，但仍无法单工具 100% 覆盖当前脚本。

### b. 建议

采用“三轨检查”：

1. `lint-md`：主检中文文案规范（空格、标点、代码块语言等）。
2. `markdownlint-cli2`：主检 Markdown 核心结构规则（MD001/MD040/MD047）。
3. 保留定制规则脚本：文件名、`.mdc` frontmatter、`## 0x01` / `### a.`、标题简洁约束。

## 0x04 实施步骤（最小化）

1. [x] 在不替换现有 Hook 的前提下并行接入 `@lint-md/cli`。
2. [x] 扫描 `knowledge/**/*.md`，评估误报 / 漏报。
3. [x] 接入 `markdownlint-cli2` 并仅启用核心规则（MD001/MD040/MD047）。
4. [x] 将可替代规则从 `check_doc_style.py` 迁移到 lint 工具，保留定制规则。
5. [x] 将 `check_doc_style.py` 瘦身到 100 行以内。

## 0x05 风险与回滚

- 风险：多工具并存可能出现重复告警。
- 回滚：保留当前 Hook，新工具先非阻塞试运行。

## 0x06 PoC 执行记录（2026-04-04）

### a. 执行命令

```shell
npx --yes @lint-md/cli --help
npx --yes @lint-md/cli AGENTS.md CLAUDE.md CODEX.md
npx --yes @lint-md/cli "knowledge/**/*.md"
```

### b. 结果摘要

- 根目录入口文档：通过（`AGENTS.md`、`CLAUDE.md`、`CODEX.md`）。
- 知识库扫描：命中 9 个 error，主要类型：
  - `no-empty-code-lang`
  - `space-around-number`
  - `no-space-in-inline-code`
- 说明：`lint-md` 能有效命中中文文案规范类问题，PoC 结论为可落地。

## 0x07 已执行改造

- 新增并集中管理配置文件到 `config/lint/`：
  - `config/lint/lint-md.json`（关闭 `no-space-in-inline-code`，避免误报阻塞）
  - `config/lint/markdownlint-cli2.jsonc`（启用 MD001/MD040/MD047，关闭其余默认规则）
- 更新 `.pre-commit-config.yaml`：
  - 新增 `lint-md` Hook：`npx --yes @lint-md/cli`
  - 新增 `markdownlint-cli2` Hook：`npx --yes markdownlint-cli2`
  - 保留 `check-doc-style` Hook 作为仓库定制规则兜底
- 精简 `scripts/check_doc_style.py`（当前 97 行），移除与 lint 工具重叠的规则，保留仓库定制规则：
  - 文件名规则
  - `.mdc` frontmatter 必填项
  - `## 0x01` / `### a.` 编号格式
  - 标题中 ` + ` / ` / ` 约束
- 规则同步：
  - 文档标题编号改为全局强制 `0x`（取消结构性豁免）
  - `.cursor/rules/general.mdc` 明确三轨检查约定
- CI 同步：
  - `.github/workflows/docs-style-check.yml` 改为直接执行 `pre-commit run --from-ref --to-ref`
  - 采用增量检查（changed files only），并补齐 Python / Node / pre-commit 安装步骤

## 0x08 参考（官方）

- ruanyf 文档规范：https://github.com/ruanyf/document-style-guide
- lint-md（规则来源声明与规则列表）：https://github.com/lint-md/lint-md
- lint-md CLI 包（2.x）：https://www.npmjs.com/package/@lint-md/cli
- markdownlint 规则文档（含 MD001 / MD040 / MD047）：https://github.com/DavidAnson/markdownlint
- markdownlint-cli2（CLI、配置与 pre-commit 示例）：https://github.com/DavidAnson/markdownlint-cli2

---
*制定日期：2026-04-04*
