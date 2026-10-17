import test from "node:test";
import assert from "node:assert/strict";
import { PairingGate } from "../src/pairing.js";
import { message } from "./helpers.js";
import type { IncomingMessage } from "../src/types.js";

const CODE = "ab12cd34";
function pairingMessage(
  text = `/pair ${CODE}`,
  overrides: Partial<IncomingMessage> = {},
): IncomingMessage {
  return message(text, {
    channel: "wecom",
    conversationId: "single:user",
    ...overrides,
  });
}

test("配对成功先持久化，重复指令幂等，其他用户不能重用", () => {
  const saved: string[] = [];
  const gate = new PairingGate({
    code: CODE,
    accountId: "bot",
    saveUser: (id) => {
      saved.push(id);
    },
  });
  assert.equal(gate.handle(pairingMessage()).kind, "paired");
  assert.deepEqual(saved, ["user"]);
  assert.equal(
    gate.handle(pairingMessage(`/pair ${CODE.toUpperCase()}`)).kind,
    "paired",
  );
  assert.equal(
    gate.handle(
      pairingMessage(`/pair ${CODE}`, {
        userId: "other",
        conversationId: "single:other",
      }),
    ).kind,
    "ignored",
  );
  assert.equal(gate.handle(pairingMessage("/pair 00000000")).kind, "ignored");
  assert.deepEqual(saved, ["user"]);
});

test("非目标平台、群聊、其他机器人和不匹配的私聊身份均不配对", () => {
  const saved: string[] = [];
  const gate = new PairingGate({
    code: CODE,
    accountId: "bot",
    saveUser: (id) => {
      saved.push(id);
    },
  });
  for (const overrides of [
    { channel: "terminal" },
    { conversationId: "group:room" },
    { accountId: "other-bot" },
    { conversationId: "single:other" },
    { userId: "" },
    {
      attachments: [
        { path: "/tmp/attachment", name: "attachment", mimeType: "image/png" },
      ],
    },
  ]) {
    assert.equal(
      gate.handle(pairingMessage(undefined, overrides)).kind,
      "ignored",
    );
  }
  assert.deepEqual(saved, []);
  assert.equal(gate.handle(pairingMessage()).kind, "paired");
});

test("普通消息不触发配对，无效码和多余参数不暴露正确码", () => {
  const gate = new PairingGate({
    code: CODE,
    saveUser() {
      assert.fail("不得持久化");
    },
  });
  assert.deepEqual(gate.handle(pairingMessage("hello")), { kind: "ignored" });
  assert.deepEqual(gate.handle(pairingMessage(`/pairing ${CODE}`)), {
    kind: "ignored",
  });
  for (const text of [
    "/pair",
    "/pair 00000000",
    `/pair ${CODE} extra`,
    `查看 /pair ${CODE}`,
  ]) {
    const result = gate.handle(pairingMessage(text));
    assert.notEqual(result.kind, "paired");
    if ("text" in result) assert(!result.text.includes(CODE));
  }
});

test("错误尝试每分钟全局限流，不通过换用户绕过，窗口后恢复", () => {
  let now = 0;
  const saved: string[] = [];
  const gate = new PairingGate({
    code: CODE,
    now: () => now,
    saveUser: (id) => {
      saved.push(id);
    },
  });
  for (let index = 0; index < 5; index++) {
    const id = `user-${index}`;
    assert.equal(
      gate.handle(
        pairingMessage("/pair 00000000", {
          userId: id,
          conversationId: `single:${id}`,
        }),
      ).kind,
      "failed",
    );
  }
  const blocked = gate.handle(pairingMessage());
  assert.equal(blocked.kind, "failed");
  assert("text" in blocked && blocked.text.includes("频繁"));
  assert.deepEqual(saved, []);
  now = 60_000;
  assert.equal(gate.handle(pairingMessage()).kind, "paired");
  assert.deepEqual(saved, ["user"]);
});

test("默认配对码 10 分钟到期，过期后不持久化", () => {
  let now = 0;
  let saved = false;
  const gate = new PairingGate({
    code: CODE,
    now: () => now,
    saveUser() {
      saved = true;
    },
  });
  now = 600_000;
  assert.equal(gate.handle(pairingMessage()).kind, "expired");
  assert.equal(saved, false);
});

test("已绑定用户的重复配对在有效期后仍幂等", () => {
  let now = 0;
  let saves = 0;
  const gate = new PairingGate({
    code: CODE,
    now: () => now,
    expiresMs: 1,
    saveUser() {
      saves++;
    },
  });
  assert.equal(gate.handle(pairingMessage()).kind, "paired");
  now = 100;
  assert.equal(gate.handle(pairingMessage()).kind, "paired");
  assert.equal(saves, 1);
});

test("写入失败保持未绑定，安全错误文案不包含底层异常，成功重试才消费", () => {
  let fails = true;
  const saved: string[] = [];
  const gate = new PairingGate({
    code: CODE,
    saveUser(id) {
      if (fails) throw new Error("private file path and credential");
      saved.push(id);
    },
  });
  const first = gate.handle(pairingMessage());
  assert.equal(first.kind, "failed");
  assert("text" in first && !first.text.includes("private"));
  fails = false;
  assert.equal(gate.handle(pairingMessage()).kind, "paired");
  assert.deepEqual(saved, ["user"]);
});

test("随机码格式和配置校验", () => {
  const first = new PairingGate({ saveUser() {} });
  const second = new PairingGate({ saveUser() {} });
  assert.match(first.code, /^[a-f0-9]{8}$/);
  assert.match(second.code, /^[a-f0-9]{8}$/);
  assert.notEqual(first.code, second.code);
  assert.throws(() => new PairingGate({ code: "short", saveUser() {} }));
  for (const expiresMs of [0, -1, 1.5, Infinity])
    assert.throws(() => new PairingGate({ expiresMs, saveUser() {} }));
});
