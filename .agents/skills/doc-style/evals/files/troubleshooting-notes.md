# 排障笔记

- 现象：模型在“帮我整理排障文档”这种请求下没有稳定触发文档 skill。
- 先看了 description，发现触发词只写了“Markdown 写作规范”，没有覆盖 README、PLAN、troubleshooting、润色这些具体说法。
- 又看了 skill body，发现没有固定的 polish gate，所以即使触发了，交付质量也不稳定。
- 修复思路：
  - 扩 description，把创建需求、问题排查、方案、文档润色都写进去。
  - 在 SKILL.md 里加入对象判定和 polish gate。
  - 做 trigger eval，确认该触发的触发，不该触发的不误命中。
- 回归时最好检查 lint-md、markdownlint-cli2、check_doc_style.py。
