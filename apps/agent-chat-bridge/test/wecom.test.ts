import test from "node:test";
import assert from "node:assert/strict";
import { setTimeout as delay } from "node:timers/promises";
import {
  DeliveryQueue,
  WeComReply,
  normalizeWeCom,
  splitUtf8,
} from "../src/channels/wecom.js";
import type { TextMessage, WSClient, WsFrame } from "@wecom/aibot-node-sdk";
import { logger } from "./helpers.js";
import { renderProgress } from "../src/channels/progress.js";

function sender(failStream = false, failPush = false) {
  const streams: Array<{
      id: string;
      text: string;
      finish: boolean | undefined;
    }> = [],
    pushes: Array<{ target: string; text: string }> = [];
  const client: Pick<WSClient, "replyStream" | "sendMessage"> = {
    async replyStream(_frame, id, text, finish) {
      if (failStream) throw new Error("stream failed");
      streams.push({ id, text, finish });
      return { headers: { req_id: "ack" } };
    },
    async sendMessage(target, body) {
      if (failPush) throw new Error("push failed");
      assert.equal(body.msgtype, "markdown");
      if (body.msgtype === "markdown")
        pushes.push({ target, text: body.markdown.content });
      return { headers: { req_id: "ack" } };
    },
  };
  return { client, streams, pushes };
}
const frame = { headers: { req_id: "request-1" } };

test("本地文件引用在流式与主动推送中均不交付为失效超链接", async () => {
  for (const failStream of [false, true]) {
    const mock = sender(failStream);
    const reply = new WeComReply(
      mock.client,
      new DeliveryQueue(0),
      frame,
      "user",
      logger,
    );
    const content =
      "**方案已更新。**\n\n[方案](/root/project/PLAN.md)\n[官方](https://example.com/doc)";
    const progress = {
      content: "[配置](private/configs/persona.md)",
      active: true,
    };
    await reply.update(content, progress);
    await reply.finish(content, progress);
    const delivered = [
      ...mock.streams.map((s) => s.text),
      ...mock.pushes.map((s) => s.text),
    ];
    assert(delivered.length);
    assert(delivered.every((text) => !/\]\((?:\/root|private\/)/.test(text)));
    assert(delivered.at(-1)?.includes("方案（`/root/project/PLAN.md`）"));
    assert(delivered.at(-1)?.includes("[官方](https://example.com/doc)"));
  }
});

test("流更新合并、固定 stream ID、终态只发一次", async () => {
  const mock = sender(),
    reply = new WeComReply(
      mock.client,
      new DeliveryQueue(0),
      frame,
      "target",
      logger,
      1000,
      10000,
    );
  await reply.update("start");
  await reply.update("old");
  await reply.update("new");
  await reply.finish("final");
  await reply.finish("duplicate");
  assert.deepEqual(
    mock.streams.map((s) => s.text),
    ["start", "final"],
  );
  assert.equal(mock.streams[0]?.id, mock.streams[1]?.id);
  assert.equal(mock.streams[1]?.finish, true);
  assert.deepEqual(mock.pushes, []);
});

test("长任务提前封口，终稿通过主动消息交付；UTF-8 分片不丢字节", async () => {
  const mock = sender(),
    reply = new WeComReply(
      mock.client,
      new DeliveryQueue(0),
      frame,
      "group-1",
      logger,
      1,
      10,
    );
  await reply.update("start");
  await delay(30);
  const text = "结果😀".repeat(3000);
  await reply.finish(text);
  assert(mock.streams.some((s) => s.finish && s.text.includes("仍在处理")));
  assert.equal(mock.pushes.map((s) => s.text).join(""), text);
  assert(
    mock.pushes.every(
      (s) => s.target === "group-1" && Buffer.byteLength(s.text) <= 4000,
    ),
  );
  assert.equal(splitUtf8(text, 4000).join(""), text);
});

test("流失败回退主动推送，推送失败会向上抛出", async () => {
  const mock = sender(true),
    reply = new WeComReply(
      mock.client,
      new DeliveryQueue(0),
      frame,
      "user",
      logger,
    );
  await reply.update("start");
  await reply.finish("result");
  assert.equal(mock.pushes[0]?.text, "result");
  const failed = sender(true, true),
    bad = new WeComReply(
      failed.client,
      new DeliveryQueue(0),
      frame,
      "user",
      logger,
    );
  await bad.update("start");
  await assert.rejects(bad.finish("result"));
});

test("群聊缺目标、错误机器人、缺请求 ID 全部拒绝", () => {
  const full: WsFrame<TextMessage> = {
    headers: { req_id: "req" },
    body: {
      aibotid: "bot",
      msgid: "msg",
      chattype: "group",
      chatid: "group",
      from: { userid: "user" },
      msgtype: "text" as TextMessage["msgtype"],
      text: { content: "/agent cursor" },
    },
  };
  assert.equal(normalizeWeCom(full, "bot")?.conversationId, "group:group");
  assert.equal(normalizeWeCom(full, "other"), undefined);
  assert.equal(
    normalizeWeCom({ ...full, body: { ...full.body!, chatid: "" } }, "bot"),
    undefined,
  );
  assert.equal(
    normalizeWeCom({ ...full, headers: { req_id: "" } }, "bot"),
    undefined,
  );
});

test("19,900 字节边界之后的终稿主动分段，不会静默截断", async () => {
  for (const bytes of [19900, 19901, 20000]) {
    const mock = sender(),
      output = new WeComReply(
        mock.client,
        new DeliveryQueue(0),
        frame,
        "user",
        logger,
      );
    const text = "a".repeat(bytes);
    await output.finish(text);
    if (bytes === 19900) assert.equal(mock.streams[0]?.text, text);
    else assert.equal(mock.pushes.map((item) => item.text).join(""), text);
  }
});

test("原生思考先开启，正文和终态闭合，长任务与推送不泄漏标签", async () => {
  const mock = sender(),
    output = new WeComReply(
      mock.client,
      new DeliveryQueue(0),
      frame,
      "user",
      logger,
      1,
      10000,
    );
  const progress = { content: "核对接口", active: true };
  await output.update("", progress);
  assert.equal(mock.streams[0]?.text, "<think></think>");
  await delay(15);
  assert(mock.streams.some((s) => s.text === "<think>核对接口"));
  await output.finish("答案", progress);
  assert.equal(mock.streams.at(-1)?.text, "<think>核对接口</think>\n\n答案");
  const safe = renderProgress(
    "答案",
    { content: "😀".repeat(1500) + "</think>恶意标签", active: true },
    true,
  );
  assert.equal((safe.match(/<think>/g) || []).length, 1);
  assert.equal((safe.match(/<\/think>/g) || []).length, 1);
  assert(Buffer.byteLength(safe) < 1600);
  const long = sender(),
    delayed = new WeComReply(
      long.client,
      new DeliveryQueue(0),
      frame,
      "user",
      logger,
      1,
      10,
    );
  await delayed.update("", progress);
  await delay(30);
  await delayed.finish("最终结果", progress);
  assert(long.streams.at(-1)?.text.includes("</think>"));
  assert.equal(long.pushes[0]?.text, "最终结果");
});

test("四个选项全部可点击，每张卡不超过三个，点击内容绑定执行器", async () => {
  const cards: any[] = [];
  const mock = sender();
  const client = {
    ...mock.client,
    async sendMessage(_target: string, body: any) {
      cards.push(body);
      return { headers: { req_id: "ack" } };
    },
  };
  const output = new WeComReply(
    client,
    new DeliveryQueue(0),
    frame,
    "user",
    logger,
  );
  const choices = Array.from({ length: 4 }, (_, i) => ({
    label: `模型 ${i + 1}`,
    command: `/model codex:model-${i + 1}`,
  }));
  await output.select("文字清单", choices);
  assert.equal(mock.streams[0]?.text, "文字清单");
  assert.equal(cards.length, 2);
  assert.deepEqual(
    cards.flatMap((c) => c.template_card.jump_list.map((j: any) => j.question)),
    choices.map((c) => c.command),
  );
  assert(cards.every((c) => c.template_card.jump_list.length <= 3));
  const fallback = new WeComReply(
    sender(false, true).client,
    new DeliveryQueue(0),
    frame,
    "user",
    logger,
  );
  await fallback.select("仍可手动选择", choices);
});
