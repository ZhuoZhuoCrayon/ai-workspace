import test from "node:test";
import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { MODEL_PRESETS, modelLabel } from "../src/agents/presets.js";
import { loadConfig } from "../src/config.js";
import { buildArguments } from "../src/agents/protocol.js";
import { temporary } from "./helpers.js";

test("两种执行器默认各四款独立模型，旧空数组配置也能直接选择", () => {
  const temp = temporary();
  try {
    const file = join(temp.directory, "bridge.local.json");
    writeFileSync(
      file,
      JSON.stringify({
        agents: { codex: { models: [] }, cursor: { models: [] } },
      }),
    );
    const config = loadConfig(file);
    assert.equal(config.agents.codex.models?.length, 4);
    assert.equal(config.agents.cursor.models?.length, 4);
    assert.equal(config.agents.codex.model, "gpt-6.1-sol");
    assert.equal(config.agents.cursor.model, "grok-4.7-xhigh-fast");
    assert.notDeepEqual(
      config.agents.codex.models,
      config.agents.cursor.models,
    );
    assert.equal(
      modelLabel("codex", config.agents.codex.model!),
      "GPT-6.1 Sol High",
    );
    assert.equal(
      modelLabel("cursor", config.agents.cursor.model!),
      "Grok 4.7 Extra High Fast",
    );
    const args = buildArguments("codex", config.agents.codex);
    assert(args.includes('model_reasoning_effort="high"'));
    assert(args.includes('service_tier="default"'));
    assert(!args.includes("--fast"));
    const full = buildArguments("codex", {
      ...config.agents.codex,
      fullAccess: true,
      networkAccess: true,
    });
    assert(full.includes("--dangerously-bypass-approvals-and-sandbox"));
    assert(!full.some((value) => value.startsWith("sandbox_mode=")));
    assert(
      !full.some((value) =>
        value.startsWith("sandbox_workspace_write.network_access="),
      ),
    );
    assert(
      buildArguments("codex", {
        ...config.agents.codex,
        networkAccess: true,
      }).includes("sandbox_workspace_write.network_access=true"),
    );
    assert.equal(
      MODEL_PRESETS.codex.filter((x) => x.id.includes("fast")).length,
      0,
    );
    writeFileSync(
      file,
      JSON.stringify({ agents: { codex: { models: ["custom"] } } }),
    );
    const custom = loadConfig(file);
    assert.deepEqual(custom.agents.codex.models, ["custom"]);
    assert.equal(custom.agents.codex.model, "custom");
    assert.equal(modelLabel("codex", "custom"), "custom");
  } finally {
    temp.cleanup();
  }
});
