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
    [{ type: "progress", content: "已完成执行命令。", active: false }],
  );
  assert.deepEqual(
    push(parser, {
      type: "item.completed",
      item: { type: "agent_message", text: "阶段结论" },
    }),
    [],
  );
  assert.deepEqual(
    push(parser, {
      type: "item.completed",
      item: { type: "agent_message", text: "最终结论" },
    }),
    [{ type: "progress", content: "阶段结论", active: false }],
  );
  assert.deepEqual(push(parser, { type: "turn.completed" }), [
    { type: "text", content: "最终结论" },
  ]);
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
  assert(args.includes("--stream-partial-output"));
  const readOnly = buildArguments("cursor", {
    command: "cursor-agent",
    writable: false,
  });
  assert(readOnly.includes("--trust"));
  assert.deepEqual(readOnly.slice(-2), ["--mode", "ask"]);
  assert(!readOnly.includes("--force"));
});

test("Codex 思考摘要按 item 更新，工具原文不进入进度或正文", () => {
  const parser = new AgentProtocol("codex");
  const item = { id: "r1", type: "reasoning", text: "核对接口" };
  push(parser, { type: "item.started", item });
  assert.deepEqual(
    push(parser, {
      type: "item.updated",
      item: { ...item, text: "核对接口和边界" },
    }),
    [{ type: "progress", content: "核对接口和边界", active: true }],
  );
  assert.deepEqual(
    push(parser, {
      type: "item.completed",
      item: { ...item, text: "核对接口和边界" },
    }),
    [{ type: "progress", content: "核对接口和边界", active: false }],
  );
  const tool = push(parser, {
    type: "item.started",
    item: {
      type: "command_execution",
      command: "secret argument",
      aggregated_output: "secret output",
    },
  });
  assert(!JSON.stringify(tool).includes("secret"));
  assert.match(JSON.stringify(tool), /核对接口和边界/);
  assert.deepEqual(
    push(parser, {
      type: "item.completed",
      item: { type: "agent_message", text: "答案" },
    }),
    [],
  );
  assert.deepEqual(push(parser, { type: "turn.completed" }), [
    { type: "text", content: "答案" },
  ]);
});

test("Cursor thinking 与 partial 正文分离，忽略重复 flush", () => {
  const parser = new AgentProtocol("cursor");
  assert.deepEqual(
    push(parser, { type: "thinking", subtype: "delta", text: "先检查" }),
    [{ type: "progress", content: "先检查", active: true }],
  );
  assert.deepEqual(push(parser, { type: "thinking", subtype: "completed" }), [
    { type: "progress", content: "先检查", active: false },
  ]);
  const assistant = (text: string, extra = {}) => ({
    type: "assistant",
    message: { content: [{ type: "text", text }] },
    ...extra,
  });
  push(parser, assistant("你", { timestamp_ms: 1 }));
  assert.deepEqual(push(parser, assistant("好", { timestamp_ms: 2 })), []);
  assert.deepEqual(
    push(parser, assistant("你好", { model_call_id: "flush" })),
    [],
  );
  assert.deepEqual(
    push(parser, { type: "result", subtype: "success", result: "你好" }),
    [{ type: "text", content: "你好" }],
  );
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

test("过程旁白只进入折叠区，正文从最终结论开始", () => {
  const codex = new AgentProtocol("codex");
  push(codex, {
    type: "item.completed",
    item: { type: "agent_message", text: "我正在读取配置。" },
  });
  const progress = push(codex, {
    type: "item.started",
    item: { type: "command_execution" },
  });
  assert(
    progress.some(
      (e) => e.type === "progress" && e.content.includes("读取配置"),
    ),
  );
  push(codex, {
    type: "item.completed",
    item: { type: "agent_message", text: "原因找到了：网络权限没有打开。" },
  });
  assert.deepEqual(push(codex, { type: "turn.completed" }), [
    { type: "text", content: "原因找到了：网络权限没有打开。" },
  ]);
  const cursor = new AgentProtocol("cursor");
  const assistant = (text: string) => ({
    type: "assistant",
    timestamp_ms: 1,
    message: { content: [{ type: "text", text }] },
  });
  push(cursor, assistant("我先看一下配置。"));
  const tools = push(cursor, { type: "tool_call", subtype: "started" });
  assert(
    tools.some(
      (e) => e.type === "progress" && e.content.includes("看一下配置"),
    ),
  );
  push(cursor, assistant("原因找到了：网络权限没有打开。"));
  assert.deepEqual(
    push(cursor, {
      type: "result",
      subtype: "success",
      result: "我先看一下配置。原因找到了：网络权限没有打开。",
    }),
    [{ type: "text", content: "原因找到了：网络权限没有打开。" }],
  );
});
