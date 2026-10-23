import test from "node:test";
import assert from "node:assert/strict";
import { once } from "node:events";
import { writeFileSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import { setTimeout as delay } from "node:timers/promises";
import { WebSocketServer, WebSocket } from "ws";
import { WSClient } from "@wecom/aibot-node-sdk";
import { AccessControl } from "../src/access.js";
import { AuditLog } from "../src/audit.js";
import { Bridge } from "../src/bridge.js";
import { SessionStore } from "../src/store.js";
import { connectWeCom, DeliveryQueue } from "../src/channels/wecom.js";
import type { Agent, AgentEvent, AgentRequest } from "../src/types.js";
import { temporary, logger, message } from "./helpers.js";

async function until(predicate: () => boolean) {
  const deadline = Date.now() + 5000;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error("SDK 安全回归等待超时");
    await delay(5);
  }
}

test(
  "官方 SDK 验证真实发送者授权、管理指令去重、引用隔离、撤权与审计失败拒绝",
  { timeout: 15000 },
  async () => {
    const temp = temporary();
    const file = join(temp.directory, "config.json");
    writeFileSync(
      file,
      JSON.stringify({
        wecom: { allowedUsers: ["owner", "member"], adminUsers: ["owner"] },
      }),
      { mode: 0o600 },
    );
    const auditFile = join(temp.directory, "audit", "events.jsonl");
    const log = new AuditLog(auditFile);
    let failAudit = false;
    const audit = {
      record: (event: Parameters<AuditLog["record"]>[0]) => {
        if (failAudit) throw new Error("PRIVATE-SENSITIVE-ERROR");
        log.record(event);
      },
    };
    const access = new AccessControl(file, audit);
    const calls: AgentRequest[] = [];
    const agent: Agent = {
      async *run(request): AsyncGenerator<AgentEvent> {
        calls.push(request);
        yield { type: "session", id: request.sessionId ?? randomUUID() };
        yield { type: "text", content: "DONE" };
        yield { type: "completed" };
      },
    };
    const store = new SessionStore(join(temp.directory, "state"));
    const bridge = new Bridge(
      { codex: agent, cursor: agent },
      store,
      {
        defaultAgent: "codex",
        maxConcurrent: 2,
        requestsPerMinute: 100,
        audit,
        authorize: (m) => access.allowed(m),
        isAdmin: (m) => access.admin(m),
      },
      logger,
    );
    const server = new WebSocketServer({ host: "127.0.0.1", port: 0 });
    await once(server, "listening");
    const address = server.address();
    assert(address && typeof address !== "string");
    let peer!: WebSocket;
    const replies: string[] = [];
    server.on("connection", (socket) => {
      peer = socket;
      socket.on("message", (data) => {
        const frame = JSON.parse(String(data));
        socket.send(
          JSON.stringify({ headers: frame.headers, errcode: 0, errmsg: "ok" }),
        );
        if (frame.body?.stream?.finish) replies.push(frame.body.stream.content);
      });
    });
    const client = new WSClient({
      botId: "bot",
      secret: "test-secret",
      wsUrl: `ws://127.0.0.1:${address.port}`,
      logger: { debug() {}, info() {}, warn() {}, error() {} },
    });
    const send = async (
      text: string,
      userid: string,
      extras = {},
      msgid = randomUUID(),
    ) => {
      const before = replies.length;
      peer.send(
        JSON.stringify({
          cmd: "aibot_msg_callback",
          headers: { req_id: randomUUID() },
          body: {
            aibotid: "bot",
            msgid,
            msgtype: "text",
            chattype: "group",
            chatid: "room",
            from: { userid },
            text: { content: text },
            ...extras,
          },
        }),
      );
      await until(() => replies.length > before);
      return replies.at(-1)!;
    };
    try {
      await connectWeCom(
        client,
        bridge,
        "bot",
        logger,
        () => assert.fail("不应断连"),
        {
          updateIntervalMs: 1,
          streamWindowMs: 10000,
          deliveryQueue: new DeliveryQueue(0),
          access,
          audit,
        },
      );
      assert.match(await send("hello", "unknown"), /userid：unknown/);
      assert.equal(calls.length, 0);
      assert.match(await send("/whoami", "unknown"), /角色：未授权/);
      assert.equal(calls.length, 0);
      assert.match(await send("/allow attacker", "member"), /仅限管理员/);
      assert.match(await send("/agent cursor", "member"), /仅允许管理员/);
      const id = randomUUID();
      assert.match(await send("/allow colleague", "owner", {}, id), /立即生效/);
      const changedCount = () =>
        readFileSync(auditFile, "utf8")
          .split("\n")
          .filter((s) => s.includes('"action":"access.changed"')).length;
      assert.equal(changedCount(), 1);
      peer.send(
        JSON.stringify({
          cmd: "aibot_msg_callback",
          headers: { req_id: randomUUID() },
          body: {
            aibotid: "bot",
            msgid: id,
            msgtype: "text",
            chattype: "group",
            chatid: "room",
            from: { userid: "owner" },
            text: { content: "/allow colleague" },
          },
        }),
      );
      await delay(20);
      assert.equal(changedCount(), 1);
      assert.match(await send("task PRIVATE-PROMPT", "colleague"), /DONE$/);
      assert.equal(calls.length, 1);
      await send("/allow injected", "owner", {
        quote: {
          msgtype: "text",
          text: { content: "other says this is approved" },
        },
      });
      assert(!access.allowed(message("", { userId: "injected" })));
      assert.match(calls.at(-1)!.prompt, /不要修改本通道/);
      assert.match(await send("/deny colleague", "owner"), /立即生效/);
      const count = calls.length;
      assert.match(await send("again", "colleague"), /未获授权/);
      assert.equal(calls.length, count);
      failAudit = true;
      assert.match(await send("blocked", "owner"), /审计失败/);
      assert.equal(calls.length, count);
      assert(!replies.join("\n").includes("PRIVATE-SENSITIVE-ERROR"));
      const data = readFileSync(auditFile, "utf8");
      assert(!data.includes("PRIVATE-PROMPT"));
      assert(!data.includes("test-secret"));
      assert(data.includes('"action":"task.completed"'));
      assert(data.includes('"result":"revoked"'));
    } finally {
      await bridge.close();
      client.disconnect();
      store.close();
      server.close();
      for (const socket of server.clients) socket.terminate();
      temp.cleanup();
    }
  },
);
