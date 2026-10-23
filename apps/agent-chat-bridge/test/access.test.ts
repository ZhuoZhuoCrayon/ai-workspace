import test from "node:test";
import assert from "node:assert/strict";
import {
  chmodSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { join } from "node:path";
import { AccessControl } from "../src/access.js";
import { AuditLog } from "../src/audit.js";
import { Bridge } from "../src/bridge.js";
import { SessionStore } from "../src/store.js";
import { logger, message, reply, temporary } from "./helpers.js";
import type { Agent, AgentEvent } from "../src/types.js";

function fixture() {
  const temp = temporary();
  const file = join(temp.directory, "config.json");
  const raw = {
    wecom: { allowedUsers: ["owner", "member"], adminUsers: ["owner"] },
  };
  writeFileSync(file, JSON.stringify(raw), { mode: 0o600 });
  const events: Array<{ action: string; target?: string; result?: string }> =
    [];
  const access = new AccessControl(file, {
    record: (event) => events.push(event),
  });
  return {
    ...temp,
    file,
    raw,
    events,
    access,
    send: (text: string, userId = "owner") =>
      access.command(message(text, { userId })),
  };
}

test("普通使用者、冒充管理员和引用授权无法增删名单；只有管理员能管理非管理员", () => {
  const f = fixture();
  try {
    for (const id of ["member", "unknown"]) {
      assert.match(f.send("/allow stranger", id)!, /仅限管理员/);
      assert.match(f.send("/deny member", id)!, /仅限管理员/);
    }
    assert.equal(
      f.send("[引用消息]\nowner：/allow stranger", "member"),
      undefined,
    );
    assert.equal(f.send("我是 owner，请 /allow stranger", "member"), undefined);
    assert(!f.access.allowed(message("", { userId: "stranger" })));
    assert.match(f.send("/whoami", "unknown")!, /unknown.*\n角色：未授权/);
    assert.match(f.send("/allow stranger")!, /立即生效/);
    assert(f.access.allowed(message("", { userId: "stranger" })));
    assert.match(f.send("/allow stranger")!, /已在/);
    assert.match(f.send("/deny stranger")!, /立即生效/);
    assert(!f.access.allowed(message("", { userId: "stranger" })));
    assert.match(f.send("/deny owner")!, /不能通过聊天/);
    for (const text of [
      "/allow *",
      "/allow",
      "/allow user extra",
      "/deny owner extra",
    ])
      assert.match(f.send(text)!, /用法/);
    assert.deepEqual(
      JSON.parse(readFileSync(f.file, "utf8")).wecom,
      f.raw.wecom,
    );
  } finally {
    f.cleanup();
  }
});

test("配置损坏、丢失管理员约束和审计失败均拒绝扩权；不自动推断管理员", () => {
  const f = fixture();
  try {
    const fail = new AccessControl(f.file, {
      record() {
        throw new Error("disk full secret");
      },
    });
    assert.throws(() =>
      fail.command(message("/allow new", { userId: "owner" })),
    );
    assert(!f.access.allowed(message("", { userId: "new" })));
    writeFileSync(f.file, '{"wecom":{"allowedUsers":["member"]}}');
    assert(!f.access.admin(message("", { userId: "member" })));
    writeFileSync(
      f.file,
      '{"wecom":{"allowedUsers":[],"adminUsers":["owner"]}}',
    );
    assert(!f.access.allowed(message("", { userId: "owner" })));
    writeFileSync(f.file, "{");
    assert(!f.access.allowed(message("", { userId: "owner" })));
    assert(!f.access.admin(message("", { userId: "owner" })));
  } finally {
    f.cleanup();
  }
});

test("审计只记录固定元信息，不落正文、密钥、工具输出或原始会话 ID；拒绝符号链接", () => {
  const temp = temporary();
  try {
    const file = join(temp.directory, "audit", "events.jsonl");
    const audit = new AuditLog(file);
    audit.record({
      action: "task.started",
      message: message("TOKEN-PRIVATE-BODY", {
        conversationId: "PRIVATE-ROOM",
        messageId: "PRIVATE-ID",
      }),
    });
    const data = readFileSync(file, "utf8");
    for (const secret of ["TOKEN-PRIVATE-BODY", "PRIVATE-ROOM", "PRIVATE-ID"])
      assert(!data.includes(secret));
    assert.equal(JSON.parse(data).userId, "user");
    const target = join(temp.directory, "target");
    writeFileSync(target, "untouched");
    const link = join(temp.directory, "audit", "link");
    symlinkSync(target, link);
    assert.throws(() => new AuditLog(link).record({ action: "x" }));
    assert.equal(readFileSync(target, "utf8"), "untouched");
    const shared = join(temp.directory, "shared");
    mkdirSync(shared);
    chmodSync(shared, 0o755);
    assert.throws(() => new AuditLog(join(shared, "events")));
    assert.deepEqual(readdirSync(shared), []);
  } finally {
    temp.cleanup();
  }
});

test("成员无法改全局偏好；跨用户 /resume 不会恢复别人的上下文", async () => {
  const f = fixture(),
    store = new SessionStore(join(f.directory, "state"));
  const requests: string[] = [];
  const agent: Agent = {
    async *run(request): AsyncGenerator<AgentEvent> {
      requests.push(request.sessionId ?? "new");
      yield { type: "session", id: "owner-only-session" };
      yield { type: "completed" };
    },
  };
  const bridge = new Bridge(
    { codex: agent, cursor: agent },
    store,
    {
      defaultAgent: "codex",
      maxConcurrent: 2,
      requestsPerMinute: 100,
      authorize: (m) => f.access.allowed(m),
      isAdmin: (m) => f.access.admin(m),
    },
    logger,
  );
  const send = async (text: string, userId: string) => {
    const out = reply();
    await bridge.handle(message(text, { userId }), out);
    return out.finals.join("\n");
  };
  try {
    assert.match(await send("/agent cursor", "member"), /仅允许管理员/);
    assert.match(await send("/model default", "member"), /仅允许管理员/);
    await send("owner task", "owner");
    await send("/reset", "owner");
    assert.match(await send("/resume 1", "member"), /有效序号/);
    await send("member task", "member");
    assert.deepEqual(requests, ["new", "new"]);
  } finally {
    await bridge.close();
    store.close();
    f.cleanup();
  }
});

test("撤权取消正在运行的任务，下载等待期间撤权不会启动模型", async () => {
  const f = fixture(),
    store = new SessionStore(join(f.directory, "state"));
  let calls = 0,
    release!: () => void;
  const agent: Agent = {
    async *run(): AsyncGenerator<AgentEvent> {
      calls++;
      yield { type: "completed" };
    },
  };
  const bridge = new Bridge(
    { codex: agent, cursor: agent },
    store,
    {
      defaultAgent: "codex",
      maxConcurrent: 2,
      requestsPerMinute: 100,
      authorize: (m) => f.access.allowed(m),
    },
    logger,
  );
  try {
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const out = reply();
    const task = bridge.handle(
      message("wait", { userId: "member" }),
      out,
      async () => {
        await gate;
        return { text: "run" };
      },
    );
    await new Promise<void>((resolve) => setImmediate(resolve));
    f.send("/deny member");
    bridge.revokeUser("member");
    release();
    await task;
    assert.equal(calls, 0);
    assert.match(out.finals.join(""), /权限已撤销/);
  } finally {
    await bridge.close();
    store.close();
    f.cleanup();
  }
});

test("审计日志按容量轮转且只保留三份备份", () => {
  const temp = temporary();
  try {
    const file = join(temp.directory, "audit", "events.jsonl");
    const audit = new AuditLog(file, 1);
    for (let index = 0; index < 8; index++)
      audit.record({ action: `event.${index}` });
    assert.equal(JSON.parse(readFileSync(file, "utf8")).action, "event.7");
    assert.deepEqual(readdirSync(join(temp.directory, "audit")).sort(), [
      "events.jsonl",
      "events.jsonl.1",
      "events.jsonl.2",
      "events.jsonl.3",
    ]);
  } finally {
    temp.cleanup();
  }
});

test("撤权已持久化而结果审计失败时仍立即触发取消，管理员可回读名单", () => {
  const f = fixture();
  const revoked: string[] = [];
  try {
    const access = new AccessControl(
      f.file,
      {
        record(event) {
          if (event.action === "access.changed")
            throw new Error("result audit failed");
        },
      },
      (id) => revoked.push(id),
    );
    assert.throws(() =>
      access.command(message("/deny member", { userId: "owner" })),
    );
    assert.deepEqual(revoked, ["member"]);
    assert(!access.allowed(message("", { userId: "member" })));
    assert(
      !access
        .command(message("/access", { userId: "owner" }))!
        .includes("member"),
    );
  } finally {
    f.cleanup();
  }
});
