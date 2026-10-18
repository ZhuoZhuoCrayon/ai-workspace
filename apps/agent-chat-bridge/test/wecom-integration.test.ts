import test from "node:test";
import assert from "node:assert/strict";
import { once } from "node:events";
import { setTimeout as delay } from "node:timers/promises";
import { WebSocketServer, WebSocket } from "ws";
import { WSClient } from "@wecom/aibot-node-sdk";
import { Bridge } from "../src/bridge.js";
import { SessionStore } from "../src/store.js";
import { connectWeCom, DeliveryQueue } from "../src/channels/wecom.js";
import type { Agent, AgentEvent, AgentRequest } from "../src/types.js";
import { temporary, logger } from "./helpers.js";

async function until(predicate: () => boolean) {
  const deadline = Date.now() + 5000;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error("测试等待超时");
    await delay(10);
  }
}

test("真实官方 SDK 经本地 WebSocket 完成认证、切换、多轮、白名单和回复", async () => {
  const temp = temporary(),
    server = new WebSocketServer({ host: "127.0.0.1", port: 0 });
  await once(server, "listening");
  const address = server.address();
  assert(address && typeof address !== "string");
  let socket: WebSocket | undefined;
  const outgoing: Array<any> = [];
  server.on("connection", (peer) => {
    socket = peer;
    peer.on("message", (data) => {
      const frame = JSON.parse(String(data));
      outgoing.push(frame);
      peer.send(
        JSON.stringify({ headers: frame.headers, errcode: 0, errmsg: "ok" }),
      );
    });
  });
  const calls: Array<{ name: string; request: AgentRequest }> = [];
  const agent = (name: string): Agent => ({
    async *run(request): AsyncGenerator<AgentEvent> {
      calls.push({ name, request });
      yield { type: "session", id: request.sessionId ?? `${name}-session` };
      yield { type: "progress", content: `${name} 正在核对边界`, active: true };
      yield { type: "text", content: `${name} 已完成` };
      yield { type: "completed" };
    },
  });
  const store = new SessionStore(temp.directory),
    bridge = new Bridge(
      { codex: agent("codex"), cursor: agent("cursor") },
      store,
      {
        defaultAgent: "codex",
        maxConcurrent: 4,
        requestsPerMinute: 100,
        timeoutMs: 1000,
        authorize: (message) => message.userId === "allowed",
        models: { codex: ["codex-only"], cursor: ["cursor-only"] },
      },
      logger,
    );
  const client = new WSClient({
    botId: "test-bot",
    secret: "test-only-placeholder",
    wsUrl: `ws://127.0.0.1:${address.port}`,
    logger: { debug() {}, info() {}, warn() {}, error() {} },
  });
  let fatal = false;
  const send = async (
    text: string,
    userid = "allowed",
    extras: Record<string, unknown> = {},
  ) => {
    const count = outgoing.filter((frame) => frame.body?.stream?.finish).length;
    socket!.send(
      JSON.stringify({
        cmd: "aibot_msg_callback",
        headers: { req_id: `test-${outgoing.length}-${Date.now()}` },
        body: {
          aibotid: "test-bot",
          msgid: crypto.randomUUID(),
          msgtype: "text",
          chattype: "single",
          from: { userid },
          text: { content: text },
          ...extras,
        },
      }),
    );
    if (userid === "allowed")
      await until(
        () =>
          outgoing.filter((frame) => frame.body?.stream?.finish).length > count,
      );
    else await delay(30);
  };
  try {
    await connectWeCom(
      client,
      bridge,
      "test-bot",
      logger,
      () => {
        fatal = true;
      },
      {
        updateIntervalMs: 1,
        streamWindowMs: 10000,
        deliveryQueue: new DeliveryQueue(0),
      },
    );
    assert(outgoing.some((frame) => frame.cmd === "aibot_subscribe"));
    await send("first");
    await send("/agent");
    await until(() => outgoing.some((frame) => frame.body?.template_card));
    const agentCard = outgoing.find((frame) => frame.body?.template_card)?.body
      .template_card;
    assert.equal(agentCard.jump_list[1].question, "/agent cursor");
    await send(agentCard.jump_list[1].question);
    await send("/model");
    assert(
      outgoing.some(
        (frame) =>
          frame.body?.stream?.content.includes("cursor-only") &&
          !frame.body.stream.content.includes("codex-only"),
      ),
    );
    await send("/model 1");
    await send("second");
    await send("/agent codex");
    await send("third");
    await send("denied", "unknown");
    assert.deepEqual(
      calls.map((call) => call.name),
      ["codex", "cursor", "codex"],
    );
    assert.equal(calls[2]?.request.sessionId, "codex-session");
    assert.equal(calls[1]?.request.sessionId, undefined);
    assert.equal(calls[1]?.request.model, "cursor-only");
    assert.equal(fatal, false);
    assert(
      outgoing.some(
        (frame) =>
          frame.body?.stream?.content ===
          "<think>cursor 正在核对边界</think>\n\ncursor 已完成",
      ),
    );
    await send("@机器人 引用排查测试", "allowed", {
      quote: { msgtype: "text", text: { content: "[该消息类型暂不能展示]" } },
    });
    assert.match(calls.at(-1)!.request.prompt, /引用原文缺失/);
    assert(
      !calls
        .at(-1)!
        .request.prompt.includes("[引用消息]\n[该消息类型暂不能展示]"),
    );
  } finally {
    await bridge.close();
    client.disconnect();
    store.close();
    for (const peer of server.clients) peer.terminate();
    await new Promise<void>((resolve) => server.close(() => resolve()));
    temp.cleanup();
  }
});
