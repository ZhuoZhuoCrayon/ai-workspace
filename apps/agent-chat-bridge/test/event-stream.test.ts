import test from "node:test";
import assert from "node:assert/strict";
import { Readable } from "node:stream";
import { readAgentEvents } from "../src/agents/event-stream.js";
import { AgentProtocol } from "../src/agents/protocol.js";

async function project(input: string) {
  const buffer = Buffer.from(input);
  const source = Readable.from(
    (function* () {
      for (let offset = 0; offset < buffer.length; offset += 4093)
        yield buffer.subarray(offset, offset + 4093);
    })(),
  );
  const result = [];
  for await (const line of readAgentEvents(source)) result.push(line);
  return result;
}

test("大型 MCP 与命令结果跨 UTF-8 分片读取，只保留状态、会话与最终答复", async () => {
  const large = '工具原文😀\\"'.repeat(150_000);
  const input = [
    { type: "thread.started", thread_id: "thread-1" },
    {
      item: {
        result: { content: [{ type: "text", text: large }] },
        arguments: large,
        id: "mcp-1",
        type: "mcp_tool_call",
      },
      type: "item.completed",
    },
    {
      type: "item.completed",
      item: { type: "command_execution", aggregated_output: large },
    },
    {
      item: { text: "已核实😀", type: "agent_message" },
      type: "item.completed",
    },
    { type: "turn.completed" },
  ]
    .map((value) => JSON.stringify(value))
    .join("\n");
  assert(Buffer.byteLength(input) > 4 * 1024 * 1024);
  const lines = await project(input);
  assert.equal(lines.length, 5);
  assert(lines.every((line) => line.length < 300));
  const parser = new AgentProtocol("codex");
  const events = lines.flatMap((line) => parser.parse(line));
  assert(parser.completed);
  assert.equal(parser.sessionId, "thread-1");
  assert(events.some((e) => e.type === "text" && e.content === "已核实😀"));
  assert(
    events.some((e) => e.type === "progress" && e.content.includes("调用工具")),
  );
});

test("Cursor 部分正文、工具大输出和最终结果保持协议语义", async () => {
  const input = [
    {
      type: "assistant",
      session_id: "cursor-1",
      timestamp_ms: 123,
      message: { content: [{ type: "text", text: "最终😀" }] },
    },
    {
      type: "tool_call",
      subtype: "completed",
      tool_call: { output: "x".repeat(2_000_000) },
    },
    { type: "result", subtype: "success", is_error: false, result: "最终😀" },
  ]
    .map((v) => JSON.stringify(v))
    .join("\r\n");
  const parser = new AgentProtocol("cursor");
  const events = (await project(input)).flatMap((line) => parser.parse(line));
  assert(parser.completed);
  assert(events.some((e) => e.type === "text" && e.content === "最终😀"));
});

test("无效与未闭合 JSON、无类型事件、超长正文仍明确失败", async () => {
  for (const input of [
    '{"type":',
    "invalid json",
    '{"type":"item.completed","item":{"result":"bad\\x"}}',
  ])
    await assert.rejects(project(input), /无效 JSON/);
  const noType = await project('{"unknown":"ignored"}');
  assert.throws(() => new AgentProtocol("codex").parse(noType[0]!), /缺少类型/);
  const parser = new AgentProtocol("codex");
  const oversized = await project(
    JSON.stringify({
      type: "item.completed",
      item: { type: "agent_message", text: "x".repeat(100_001) },
    }),
  );
  assert.throws(() => parser.parse(oversized[0]!), /回复超过长度上限/);
  await assert.rejects(
    project(
      JSON.stringify({
        type: "assistant",
        message: { content: [{ type: "text", text: "x".repeat(500_000) }] },
      }),
    ),
    /回复超过长度上限/,
  );
});
