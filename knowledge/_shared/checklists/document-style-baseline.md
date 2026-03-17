# 文档规范基线说明

## 0x01 扫描口径

- 扫描命令：`python3 scripts/check_doc_style.py --all`
- 扫描日期：`2026-03-17`
- 检查范围：工作区自有 `*.md`、`*.mdc`
- 当前豁免：`.agents/skills/**`、`.cursor/skills/**`、`.claude/skills/**`、第三方目录、依赖目录、缓存目录，以及不由本仓维护内容规范的拷贝文档

## 0x02 基线结果

- 全量扫描结果：`87` 个文件、`49` 个问题
- 当前阻断策略：`pre-commit` 与 `CI` 默认拦截新增或改动文档；历史存量问题先保留基线，不直接阻断全仓

## 0x03 热点规则

- `subsection-format`：`16`
- `concise-title`：`9`
- `section-number`：`8`
- `fence-language`：`7`
- `cjk-latin-spacing`：`4`

## 0x04 热点文件

- `knowledge/bkm-skills/issues/2026-02-15-rpc-inspection-skills/PLAN.md`：`6`
- `knowledge/bkm-skills/issues/2026-03-01-ci-helper-best-practices/PLAN.md`：`6`
- `.cursor/rules/git.mdc`：`5`
- `knowledge/bkmonitor_mcp/issues/2026-02-14-alarm-trace-mcp-new-tools/PLAN.md`：`5`
- `.cursor/rules/general.mdc`：`3`

## 0x05 后续处理建议

- 优先清理高频规则：三级标题格式、标题自然语言化、二级标题编号。
- 优先清理高热点文件：`knowledge/bkm-skills/issues/2026-02-15-rpc-inspection-skills/PLAN.md`、`knowledge/bkm-skills/issues/2026-03-01-ci-helper-best-practices/PLAN.md`。
- 新增文档继续走“规则提示 + 本地脚本 + `pre-commit` + `CI` + 人工清单”的链路。
