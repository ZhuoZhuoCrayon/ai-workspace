import assert from "node:assert/strict";
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import { cursorTiming } from "../src/agents/cursor-timing.js";
import { temporary } from "./helpers.js";

test("只记录完整 CLI 工具边界，不落盘消息正文或不完整的调用", (t) => {
  const temp = temporary();
  t.after(temp.cleanup);
  const env = { BK_APM_CURSOR_DATA_DIR: temp.directory };
  assert.equal(cursorTiming("/probe", env), undefined);
  writeFileSync(join(temp.directory, "config.json"), '{"enabled":true}');
  const run = (workspace: string, complete: boolean) => {
    const record = cursorTiming(workspace, env)!;
    record({ type: "user", session_id: "s", text: "private prompt" });
    record({ type: "tool_call", subtype: "started", call_id: "r" });
    if (complete)
      record({ type: "tool_call", subtype: "completed", call_id: "r" });
    record({ type: "assistant", text: "private response" });
    record({ type: "result", subtype: "success", result: "private response" });
  };
  run("/tmp/bridge-cursor-rules-abc123/root/good.project", true);
  run("/tmp/bridge-cursor-rules-xyz789/root/incomplete", false);
  const dir = join(temp.directory, "cli-timing");
  const files = readdirSync(dir);
  assert.equal(files.length, 1);
  const raw = readFileSync(join(dir, files[0]!), "utf8");
  assert.ok(!raw.includes("private"));
  assert.equal(JSON.parse(raw).tools[0].id, "r");
});

test("桥接器只保存工具计时，不保存模型用量与 result 合计", async (t) => {
  const { Readable } = await import("node:stream");
  const { readAgentEvents } = await import("../src/agents/event-stream.js");
  const temp = temporary();
  t.after(temp.cleanup);
  writeFileSync(join(temp.directory, "config.json"), '{"enabled":true}');
  const record = cursorTiming("/tmp/bridge-cursor-rules-abc123/root/proj", {
    BK_APM_CURSOR_DATA_DIR: temp.directory,
  })!;
  const events = [
    { type: "user", session_id: "s" },
    {
      type: "tool_call",
      subtype: "started",
      call_id: "r",
      model_call_id: "first",
    },
    {
      type: "tool_call",
      subtype: "completed",
      call_id: "r",
      model_call_id: "first",
    },
    {
      type: "usage",
      subtype: "model_call",
      model_call_id: "first",
      usage: { inputTokens: 4, outputTokens: 76, apiKey: "not-recorded" },
    },
    { type: "assistant", model_call_id: "final" },
    {
      type: "usage",
      subtype: "model_call",
      model_call_id: "final",
      usage: { inputTokens: 2, outputTokens: 15 },
    },
    {
      type: "result",
      subtype: "success",
      usage: { inputTokens: 6, outputTokens: 91 },
    },
  ];
  for await (const _ of readAgentEvents(
    Readable.from(events.map((e) => JSON.stringify(e) + "\n")),
    undefined,
    record,
  )) {
  }
  const dir = join(temp.directory, "cli-timing");
  const raw = JSON.parse(readFileSync(join(dir, readdirSync(dir)[0]!), "utf8"));
  assert.equal(raw.calls, undefined);
  assert.equal(raw.tools[0].modelCallId, undefined);
  assert.equal(raw.finalModelCallId, undefined);
  assert.equal(raw.tools[0].id, "r");
});
