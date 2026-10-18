import test from "node:test";
import assert from "node:assert/strict";
import { portableLinks } from "../src/channels/links.js";

test("本地链接保留可读路径，不伪造 public 或 private 远程地址", () => {
  for (const path of [
    "/root/project/PLAN.md",
    "private/configs/persona.md",
    "../PLAN.md",
    "./PLAN.md",
    "file:///root/project/PLAN.md",
    "vscode://file/root/project/PLAN.md",
    "codex://review",
    "C:\\project\\PLAN.md",
  ]) {
    assert.equal(portableLinks(`[方案](${path})`), `方案（\`${path}\`）`);
  }
  assert.equal(
    portableLinks("[PLAN.md](</path with spaces/PLAN.md>)"),
    "PLAN.md（`/path with spaces/PLAN.md`）",
  );
  assert.equal(
    portableLinks("[方案](/root/设计(v2)/PLAN.md:12)"),
    "方案（`/root/设计(v2)/PLAN.md:12`）",
  );
});

test("团队知识、源码与官方 HTTPS 引用保持原样", () => {
  const input = [
    "[团队说明](https://wiki.example.com/pages/viewpage.action?pageId=123)",
    "[源码](https://github.com/org/project/blob/main/README.md#usage)",
    "[私有方案](https://git.example.com/team/private/blob/master/PLAN.md)",
    "[官方文档](https://developers.openai.com/codex/cli)",
  ].join("\n");
  assert.equal(portableLinks(input), input);
});

test("引用式本地链接和本地自动链接降级，代码与图片语法保留", () => {
  const text = "[说明][doc]\n[doc]: /root/PLAN.md\n<file:///root/PLAN.md>";
  assert.equal(
    portableLinks(text),
    "说明（`/root/PLAN.md`）\n\n`file:///root/PLAN.md`",
  );
  const code =
    "```markdown\n[示例](/root/PLAN.md)\n```\n`[行内](/root/PLAN.md)`\n![图片](/root/result.png)";
  assert.equal(portableLinks(code), code);
  assert.equal(
    portableLinks("[来源][web]\n[web]: https://example.com/doc"),
    "[来源][web]\n[web]: https://example.com/doc",
  );
});
