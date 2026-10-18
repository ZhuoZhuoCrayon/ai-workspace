import test from "node:test";
import assert from "node:assert/strict";
import { Bridge } from "../src/bridge.js";
import { SessionStore } from "../src/store.js";
import type { Agent, AgentEvent, AgentRequest } from "../src/types.js";
import { logger, message, reply, temporary } from "./helpers.js";

class RecordingAgent implements Agent {
  requests: AgentRequest[] = [];
  constructor(private name: string) {}
  async *run(request: AgentRequest): AsyncGenerator<AgentEvent> {
    this.requests.push(request);
    yield {
      type: "session",
      id: request.sessionId ?? `${this.name}-${this.requests.length}`,
    };
    yield { type: "text", content: `${this.name}: ${request.prompt}` };
    yield { type: "completed" };
  }
}
const options = {
  defaultAgent: "codex" as const,
  maxConcurrent: 2,
  requestsPerMinute: 100,
  timeoutMs: 2000,
  authorize: () => true,
};

test("对话端编号切换执行器，模型目录、偏好与旧卡片按执行器隔离", async () => {
  const temp = temporary(),
    store = new SessionStore(temp.directory);
  const codex = new RecordingAgent("codex"),
    cursor = new RecordingAgent("cursor");
  const settings = {
    ...options,
    models: { codex: ["cx-a", "cx-b"], cursor: ["cu-a", "cu-b"] },
  };
  let bridge = new Bridge({ codex, cursor }, store, settings, logger);
  const choices: Array<{ label: string; command: string }> = [];
  const send = async (text: string) => {
    const output = reply();
    output.select = async (content, items) => {
      choices.splice(0, choices.length, ...items);
      await output.finish(content);
    };
    await bridge.handle(message(text), output);
    return output.finals[0]!;
  };
  try {
    assert.match(await send("/agent"), /1\. codex.*\n2\. cursor/);
    assert.equal(choices[1]?.command, "/agent cursor");
    assert.match(await send("/model"), /cx-a/);
    const oldCard = choices[0]!.command;
    await send("/model 2");
    await send("codex task");
    assert.equal(codex.requests[0]?.model, "cx-b");
    await send("/agent 2");
    const models = await send("/model");
    assert.match(models, /cu-a/);
    assert(!models.includes("cx-a"));
    assert.match(await send(oldCard), /属于 codex/);
    assert.match(await send("/model cx-b"), /不在/);
    await send("/model 1");
    await send("cursor task");
    assert.equal(cursor.requests[0]?.model, "cu-a");
    await send("/agent 1");
    await send("continue");
    assert.equal(codex.requests[1]?.model, "cx-b");
    assert.equal(codex.requests[1]?.sessionId, "codex-1");
    await bridge.close();
    store.close();
    const resumedStore = new SessionStore(temp.directory);
    bridge = new Bridge({ codex, cursor }, resumedStore, settings, logger);
    try {
      assert.match(await send("/model"), /当前模型：cx-b/);
      await send("/model default");
      await send("default task");
      assert.equal(codex.requests[2]?.model, undefined);
    } finally {
      await bridge.close();
      resumedStore.close();
    }
  } finally {
    await bridge.close();
    store.close();
    temp.cleanup();
  }
});

test("切换执行器后恢复各自上下文，重启和 reset 可预测", async () => {
  const temp = temporary();
  let store = new SessionStore(temp.directory);
  const codex = new RecordingAgent("codex"),
    cursor = new RecordingAgent("cursor");
  let bridge = new Bridge({ codex, cursor }, store, options, logger);
  const send = async (text: string) => {
    const output = reply();
    await bridge.handle(message(text), output);
    return output;
  };
  try {
    await send("first");
    await send("/agent cursor");
    await send("second");
    await send("/agent codex");
    await send("third");
    assert.equal(codex.requests[1]?.sessionId, "codex-1");
    assert.equal(cursor.requests[0]?.sessionId, undefined);
    await bridge.close();
    store.close();
    store = new SessionStore(temp.directory);
    bridge = new Bridge({ codex, cursor }, store, options, logger);
    await send("after restart");
    assert.equal(codex.requests[2]?.sessionId, "codex-1");
    await send("/reset");
    await send("fresh");
    assert.equal(codex.requests[3]?.sessionId, undefined);
    assert.match((await send("/agent unknown")).finals[0]!, /命令无效/);
    assert.equal(codex.requests.length, 4);
  } finally {
    await bridge.close();
    store.close();
    temp.cleanup();
  }
});

test("机器人、用户、群会话和平台隔离，重复消息不执行", async () => {
  const temp = temporary();
  const store = new SessionStore(temp.directory),
    codex = new RecordingAgent("codex");
  const bridge = new Bridge({ codex, cursor: codex }, store, options, logger);
  try {
    const first = message("one");
    await bridge.handle(first, reply());
    await bridge.handle(first, reply());
    for (const overrides of [
      { userId: "another" },
      { accountId: "another" },
      { channel: "another" },
      { conversationId: "another" },
    ])
      await bridge.handle(message("isolated", overrides), reply());
    assert.equal(codex.requests.length, 5);
    assert(codex.requests.every((request) => request.sessionId === undefined));
  } finally {
    await bridge.close();
    store.close();
    temp.cleanup();
  }
});

test("忙碌会话拒绝切换、并发有上限、cancel 可恢复空闲", async () => {
  const temp = temporary(),
    store = new SessionStore(temp.directory);
  let started!: () => void;
  const ready = new Promise<void>((resolve) => (started = resolve));
  const slow: Agent = {
    async *run(request) {
      started();
      await new Promise<void>((resolve) =>
        request.signal.addEventListener("abort", () => resolve(), {
          once: true,
        }),
      );
      request.signal.throwIfAborted();
      yield { type: "completed" };
    },
  };
  const bridge = new Bridge(
    { codex: slow, cursor: slow },
    store,
    { ...options, maxConcurrent: 1 },
    logger,
  );
  try {
    const taskReply = reply();
    const task = bridge.handle(message("long task"), taskReply);
    await ready;
    const switching = reply();
    await bridge.handle(message("/agent cursor"), switching);
    assert.match(switching.finals[0]!, /运行期间/);
    const other = reply();
    await bridge.handle(message("another", { userId: "other" }), other);
    assert.match(other.finals[0]!, /并发/);
    const cancel = reply();
    await bridge.handle(message("/cancel"), cancel);
    await task;
    assert.match(taskReply.finals[0]!, /已取消/);
    const status = reply();
    await bridge.handle(message("/status"), status);
    assert.match(status.finals[0]!, /空闲/);
  } finally {
    await bridge.close();
    store.close();
    temp.cleanup();
  }
});

test("白名单在创建状态前生效，限频不调用 Agent", async () => {
  const temp = temporary(),
    store = new SessionStore(temp.directory),
    codex = new RecordingAgent("codex");
  const bridge = new Bridge(
    { codex, cursor: codex },
    store,
    { ...options, requestsPerMinute: 1, authorize: (m) => m.userId === "user" },
    logger,
  );
  try {
    const denied = reply();
    await bridge.handle(message("no", { userId: "denied" }), denied);
    assert.deepEqual(denied.finals, []);
    await bridge.handle(message("allowed"), reply());
    const limited = reply();
    await bridge.handle(message("limited"), limited);
    assert.match(limited.finals[0]!, /频繁/);
    assert.equal(codex.requests.length, 1);
  } finally {
    await bridge.close();
    store.close();
    temp.cleanup();
  }
});

test("任务已用尽配额时仍可取消，附件准备只在准入成功后执行", async () => {
  const temp = temporary(),
    store = new SessionStore(temp.directory),
    agent = new RecordingAgent("codex");
  const bridge = new Bridge(
    { codex: agent, cursor: agent },
    store,
    { ...options, requestsPerMinute: 1 },
    logger,
  );
  let prepares = 0;
  const incoming = message("");
  const prepare = async () => {
    prepares++;
    return await new Promise<{ text: string }>(() => {});
  };
  try {
    const result = reply(),
      task = bridge.handle(incoming, result, prepare);
    await new Promise((resolve) => setTimeout(resolve, 10));
    await bridge.handle(incoming, reply(), prepare);
    await bridge.handle(message("another"), reply(), prepare);
    assert.equal(prepares, 1);
    await bridge.handle(message("/cancel"), reply());
    await Promise.race([
      task,
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error("取消未结束")), 200),
      ),
    ]);
    assert.match(result.finals[0]!, /已取消/);
    assert.equal(agent.requests.length, 0);
  } finally {
    await bridge.close();
    store.close();
    temp.cleanup();
  }
});

test("prepare 永不返回也能硬超时并释放任务槽", async () => {
  const temp = temporary(),
    store = new SessionStore(temp.directory),
    agent = new RecordingAgent("codex");
  const bridge = new Bridge(
    { codex: agent, cursor: agent },
    store,
    { ...options, timeoutMs: 20 },
    logger,
  );
  try {
    const output = reply();
    await Promise.race([
      bridge.handle(message(""), output, () => new Promise(() => {})),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error("硬超时未生效")), 200),
      ),
    ]);
    assert.match(output.finals[0]!, /超时/);
    assert.equal(bridge.snapshot().running, 0);
  } finally {
    await bridge.close();
    store.close();
    temp.cleanup();
  }
});

test("rerun 保留图片/文件输入，model 与历史按执行器隔离", async () => {
  const temp = temporary(),
    store = new SessionStore(temp.directory),
    codex = new RecordingAgent("codex"),
    cursor = new RecordingAgent("cursor");
  const bridge = new Bridge(
    { codex, cursor },
    store,
    { ...options, models: { codex: ["model-a"], cursor: ["model-b"] } },
    logger,
  );
  const send = async (
    text: string,
    attachments?: import("../src/types.js").Attachment[],
  ) => {
    const output = reply();
    await bridge.handle(
      message(text, attachments ? { attachments } : {}),
      output,
    );
    return output;
  };
  try {
    const attachments = [
      { path: "/tmp/image.png", name: "image.png", mimeType: "image/png" },
      { path: "/tmp/file.txt", name: "file.txt", mimeType: "text/plain" },
    ];
    await send("/model model-a");
    await send("review attachments", attachments);
    await send("/rerun");
    assert.deepEqual(codex.requests[0]?.images, codex.requests[1]?.images);
    assert.match(codex.requests[1]!.prompt, /file.txt/);
    assert.equal(codex.requests[1]?.model, "model-a");
    await send("/reset");
    await send("new question");
    assert.match((await send("/sessions")).finals[0]!, /review attachments/);
    await send("/resume 1");
    await send("resume question");
    assert.equal(codex.requests.at(-1)?.sessionId, "codex-1");
    await send("/agent cursor");
    await send("cursor question");
    assert.equal(cursor.requests[0]?.model, undefined);
    assert.equal(cursor.requests[0]?.sessionId, undefined);
  } finally {
    await bridge.close();
    store.close();
    temp.cleanup();
  }
});
