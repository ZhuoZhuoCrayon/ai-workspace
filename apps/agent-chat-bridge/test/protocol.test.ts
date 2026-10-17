import test from "node:test";
import assert from "node:assert/strict";
import { AgentProtocol, buildArguments } from "../src/agents/protocol.js";

const push = (parser: AgentProtocol, event: unknown) =>
  parser.parse(JSON.stringify(event));

test("Codex 文本、工具与终态隔离，恢复命令绑定具体 ID", () => {
  const parser = new AgentProtocol("codex");
  assert.deepEqual(
    push(parser, { type: "thread.started", thread_id: "thread-1" }),
    [{ type: "session", id: "thread-1" }],
  );
  assert.deepEqual(
    push(parser, {
      type: "item.completed",
      item: {
        type: "command_execution",
        aggregated_output: "private tool output",
      },
    }),
    [],
  );
  assert.deepEqual(
    push(parser, {
      type: "item.completed",
      item: { type: "agent_message", text: "阶段结论" },
    }),
    [{ type: "text", content: "阶段结论" }],
  );
  assert.deepEqual(
    push(parser, {
      type: "item.completed",
      item: { type: "agent_message", text: "最终结论" },
    }),
    [{ type: "text", content: "阶段结论\n\n最终结论" }],
  );
  push(parser, { type: "turn.completed" });
  assert.equal(parser.completed, true);
  const args = buildArguments(
    "codex",
    { command: "codex", writable: false },
    "thread-1",
  );
  assert.deepEqual(args.slice(-3), ["resume", "thread-1", "-"]);
  assert(!args.includes("--last"));
  assert(args.includes('sandbox_mode="read-only"'));
});

test("Cursor 以终态文本为准，工具输出不进入正文", () => {
  const parser = new AgentProtocol("cursor");
  push(parser, { type: "system", subtype: "init", session_id: "cursor-1" });
  push(parser, {
    type: "assistant",
    message: { content: [{ type: "text", text: "阶段结果" }] },
  });
  push(parser, {
    type: "tool_call",
    tool_call: { readToolCall: { result: { secret: "tool output" } } },
  });
  assert.deepEqual(
    push(parser, {
      type: "result",
      subtype: "success",
      is_error: false,
      result: "最终结果",
      session_id: "cursor-1",
    }),
    [{ type: "text", content: "最终结果" }],
  );
  assert.equal(parser.completed, true);
  const args = buildArguments(
    "cursor",
    { command: "cursor-agent", writable: true },
    "cursor-1",
  );
  assert(args.includes("--force"));
  assert(args.includes("--trust"));
  assert.deepEqual(args.slice(-2), ["--resume", "cursor-1"]);
  assert(!args.includes("--stream-partial-output"));
  const readOnly = buildArguments("cursor", {
    command: "cursor-agent",
    writable: false,
  });
  assert(readOnly.includes("--trust"));
  assert.deepEqual(readOnly.slice(-2), ["--mode", "ask"]);
  assert(!readOnly.includes("--force"));
});

test("格式、会话 ID、输出上限和失败终态都拒绝", () => {
  assert.throws(
    () => new AgentProtocol("codex").parse("not json"),
    /无效 JSON/,
  );
  assert.throws(
    () =>
      push(new AgentProtocol("codex"), {
        type: "thread.started",
        thread_id: "--last",
      }),
    /会话 ID/,
  );
  assert.throws(
    () =>
      push(new AgentProtocol("codex", 3), {
        type: "item.completed",
        item: { type: "agent_message", text: "1234" },
      }),
    /长度上限/,
  );
  assert.throws(
    () =>
      push(new AgentProtocol("cursor"), {
        type: "result",
        subtype: "error",
        is_error: true,
      }),
    /失败/,
  );
  assert.throws(
    () => push(new AgentProtocol("codex"), { type: "turn.failed" }),
    /失败/,
  );
});
