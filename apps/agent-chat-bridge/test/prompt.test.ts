import test from "node:test";
import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { loadConfig } from "../src/config.js";
import { buildPrompt } from "../src/prompt.js";
import { temporary } from "./helpers.js";

test("人格文件按配置目录读取，两种执行器使用同一表达约定且保留任务边界", () => {
  const temp = temporary();
  try {
    writeFileSync(
      join(temp.directory, "persona.md"),
      "先接住对方的问题，再给可靠的下一步；不编造进展。",
    );
    const file = join(temp.directory, "bridge.local.json");
    writeFileSync(
      file,
      JSON.stringify({
        personaFile: "persona.md",
        agents: { codex: { fullAccess: true } },
      }),
    );
    const cfg = loadConfig(file);
    assert.equal(cfg.agents.codex.fullAccess, true);
    const prompt = buildPrompt("用户任务", [], cfg.persona);
    assert(prompt.includes(cfg.persona));
    assert.match(prompt, /只执行用户明确提出的任务/);
    assert.match(prompt, /优先使用已登录的 gh CLI/);
    assert(prompt.endsWith("用户任务"));
    writeFileSync(join(temp.directory, "persona.md"), "x".repeat(16001));
    assert.throws(() => loadConfig(file), /16,000/);
    assert.match(buildPrompt("任务", []), /不编造原因/);
  } finally {
    temp.cleanup();
  }
});
