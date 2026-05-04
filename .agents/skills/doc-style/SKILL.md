---
name: doc-style
description: 结构化编写、重构、润色和验收 Markdown / MDC 文档。只要用户要创建、编辑、润色、改写、评审或整理任何 `.md` / `.mdc` 文件，或提到 issue / plan / troubleshooting / snippet、规则文档、PR review 评论、GitHub 评论、零散草稿结构化，就应使用这个 skill。
---

# Doc Style

## 0x01 定位

`doc-style` 负责 Markdown / MDC 文档的结构设计、表达压缩、对象适配与交付前润色。

适用范围：

- 文件范围：所有 `.md` / `.mdc` 文档编辑、重构、润色与验收。
- 知识文档类型：issue、plan、troubleshooting、snippet。
- 其他文档类型：规则文档、普通说明文档。
- 短交付：PR review 评论、GitHub 评论、零散草稿的结构化压缩。

职责边界：

- 只处理文档内容、结构和表达。
- 不负责外部资产定位、元数据治理或发布流程。

## 0x02 通用必读

【CRITICAL（必须执行，不可协商）】无论文档类型是什么，都必须先读 `references/common/` 下全部 `5` 个文件：

- `references/common/title.md`
- `references/common/text.md`
- `references/common/paragraph.md`
- `references/common/number.md`
- `references/common/marks.md`

## 0x03 类型识别与专项规则

先识别文档类型再读取对应专项规则。

通用 Markdown / MDC 与 PR review / GitHub 评论默认只用 `common/`。

| 文档类型 | 识别线索 | 专项规则 |
| --- | --- | --- |
| issue | 需求定义、issue README、目标 / 范围 / 非目标 / 验收 | `issue-readme-writing.md` |
| plan | `PLAN.md`、方案、计划、架构设计、开发方案、调研结论、开发落点、风险与进展 | `plan-writing.md` |
| troubleshooting | 问题排查、故障复盘、根因链路 | `troubleshooting-writing.md` |
| snippet | 代码片段、命令片段、协议片段 | `snippet-writing.md` |

## 0x04 写作流程

1. **判定类型**：识别文档类型与目标读者，明确要读取的专项规则。
2. **读取规范**：先读 `common/` 全部 `5` 个文件，再读专项规则。
3. **完成初稿**：按规范写作。
4. **润色与自检**：见 `0x05`。

## 0x05 润色与自检

完成初稿后执行润色闭环：

1. **规范回扫**：用 `common/` 与对应专项规则逐节核对，违例就地修复。
2. **闭卷通读**：从目标读者视角通读初稿，确认读者不需要追问「结构长什么样」「字段在哪一层」「下一步做什么」。
3. **主观清单**：按下表列出 `5` 张主观审稿清单。

【CRITICAL（必须执行，不可协商）】审稿自检不能用自动检查替代。

清单执行约束：

- **只列举问题点，不直接改文档**：由作者评估后再决定是否采纳。
- 每条问题点给出原文位置（小节号或原句片段）和建议替换 / 改写方向。
- 无问题时写"无"：不省略清单。

| 清单 | 定义 | 判定要点 |
| --- | --- | --- |
| 黑话清单 | 仅在特定圈层成立、脱离圈层即丢失语义的词语 | 圈外读者无法独立读懂，依赖默会知识、内部缩写、外文夹杂或隐喻 |
| 晦涩清单 | 读完仍需回看才能理解的语句 | 术语堆叠、被动嵌套、省略主语、长定语前置 |
| 冗余清单 | 对结论无新增信息量的内容 | 过程叙述、跨节重述、为衔接而衔接的句子 |
| AI 味清单 | 模板化、与具体上下文脱钩也照样成立的表达 | 句子换主题仍然读得通，或堆积空泛形容词与机械承接转折 |
| 审美缺点清单 | 以「极高文档审美的专业领域评审专家」视角列出的缺点 | 结构、行文、叙事节奏、信息层级、留白与对齐 |

## 0x06 交付前检查

执行三轨自动检查：`lint-md`、`markdownlint-cli2`、`scripts/check_doc_style.py`。

`pre-commit run --files <doc-path-1> <doc-path-2> ...`

命令失败时先修文档再重跑直到通过。

交付时简短说明：

- 文档类型与本次读取的专项规则。
- 是否执行了润色与主观清单自检。
- `pre-commit` 是否通过：未通过时说明阻塞原因。
