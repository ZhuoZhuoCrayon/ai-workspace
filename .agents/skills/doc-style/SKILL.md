---
name: doc-style
description: 结构化编写、重构、润色和验收 Markdown 文档。只要用户提到“帮我创建一个需求/问题排查/方案/文档”、写 `README.md` / `PLAN.md` / `troubleshooting` / `snippet`、润色或改写 Markdown 文档、整理 PR review 评论 / GitHub 评论、或把零散草稿整理成结构化文档，就应使用这个 skill。知识对象场景先经 `knowledge_mgr` 明确对象职责，再用本 skill 完成结构设计、表达打磨和交付前润色。
---

# Doc Style

## 0x01 定位

- 负责 Markdown 文档的结构设计、表达压缩、对象适配与交付前润色。
- 也适用于 PR review 评论、GitHub 评论等短篇 Markdown 交付物的结构化压缩。
- 不负责知识对象的定位、索引、frontmatter 治理或写回流程。
- 这些职责仍由 `knowledge_mgr` 承接。
- 遇到知识对象场景时，先读 `../knowledge_mgr/SKILL.md`。
- 必要时再读 `../knowledge_mgr/references/operation-rules.md`，确认对象职责和写回边界。

## 0x02 文档类型判定

先识别交付物类型，再读取对应 reference，不要一次性读取全部 reference。

【CRITICAL（必须执行，不可协商）】无论交付物类型是什么，都必须先读 `common-writing.md`。

| 文档类型 | 必读 reference | 按需补读 | 说明 |
| --- | --- | --- | --- |
| 通用 Markdown | `common-writing.md` | 无 | 所有 Markdown 文档的基础规则入口。 |
| `README.md` / 需求文档 | `common-writing.md`、`issue-readme-writing.md` | `../knowledge_mgr/references/operation-rules.md` | 知识对象场景先确认对象职责，再写需求主干。 |
| `PLAN.md` / 实施方案 | `common-writing.md`、`plan-writing.md` | `exemplars.md`、`../knowledge_mgr/references/operation-rules.md` | 需要校准结构密度时再读 `exemplars.md`。 |
| `troubleshooting` | `common-writing.md`、`troubleshooting-writing.md` | `../knowledge_mgr/references/operation-rules.md` | 知识对象场景先确认写回边界。 |
| `snippet` | `common-writing.md`、`snippet-writing.md` | `../knowledge_mgr/references/operation-rules.md` | 知识对象场景先确认对象职责和归档边界。 |
| PR review 评论 / GitHub 评论 | `common-writing.md` | 无 | 先写 review 结论，再按信息形态选择叙述、列表或表格，不把全文硬改成表格。 |

## 0x03 写作工作流

1. 先判定文档类型、目标读者和交付物职责。
2. 读取 `common-writing.md` 与对象特化 reference。
3. 知识对象场景先确认 `knowledge_mgr` 的对象规则。
4. 先写主干结论，再补充支撑信息，让读者只读主干也能获得当前有效结论。
5. 将并列信息改写为列表或表格，不把多层逻辑塞进一个段落。
6. 当内容是“对象 -> 处理动作 / 必读文档 / 规则入口 / 文件归属”的映射关系时，必须优先表格化。
7. 若输入是零散草稿，先归并重复信息，再重写标题层级和段落结构。
8. 若文档承担评审职责，默认补齐验收、风险、验证或下一步动作。
9. PR review 评论场景，优先保留根因链路的叙述性表达，并把修复点、对比项等横向信息表格化。

## 0x04 Polish Gate

完成初稿后，必须执行一次固定润色闭环：

1. 回读本次使用过的 reference。
2. `PLAN.md` 场景额外回读 [exemplars.md](references/exemplars.md) 中的评测基线，校准结构密度与表格化承载方式。
3. 逐段压缩句子，只保留可判定、可复用、可验证的信息。
4. 检查章节职责是否混淆，例如不要把需求主干写进 `PLAN.md`，也不要把调研细节写进 `README.md`。
5. 将可结构化的信息尽量收进列表或表格，并消除口语化、自述式表达。

## 0x05 交付前检查

- 默认执行以下命令。
- 若命令失败，先修正文档再重新执行，直到通过。

`pre-commit run --files <doc-path-1> <doc-path-2> ...`

交付时给出简短说明：

- 文档类型与本次读取的 reference。
- 是否执行了 polish gate。
- `pre-commit` 是否通过。
- 若未跑通，明确说明阻塞原因。
