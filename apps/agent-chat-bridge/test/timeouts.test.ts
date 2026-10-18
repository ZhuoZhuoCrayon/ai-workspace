import test from "node:test";
import assert from "node:assert/strict";
import { setImmediate as turn } from "node:timers/promises";
import { Bridge } from "../src/bridge.js";
import { SessionStore } from "../src/store.js";
import { CliAgent } from "../src/agents/cli-agent.js";
import type { Agent, AgentRequest } from "../src/types.js";
import { executable, logger, message, reply, temporary } from "./helpers.js";

const settings = {
  defaultAgent: "codex" as const,
  maxConcurrent: 2,
  requestsPerMinute: 100,
  authorize: () => true,
};

test("WTB 默认时限：实际活动可持续超过 10 分钟，60 分钟仍强制结束", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const temp = temporary(),
    store = new SessionStore(temp.directory);
  let request!: AgentRequest;
  const agent: Agent = {
    async *run(input) {
      request = input;
      await new Promise<void>((resolve) =>
        input.signal.addEventListener("abort", () => resolve(), { once: true }),
      );
      input.signal.throwIfAborted();
    },
  };
  const bridge = new Bridge(
    { codex: agent, cursor: agent },
    store,
    settings,
    logger,
  );
  const output = reply();
  const running = bridge.handle(message("long task"), output);
  try {
    await turn();
    for (let minute = 1; minute < 60; minute++) {
      t.mock.timers.tick(60_000);
      request.onActivity?.();
      assert.equal(request.signal.aborted, false);
    }
    t.mock.timers.tick(60_000);
    await running;
    assert.match(output.finals[0]!, /总时限（3600 秒）/);
    assert.equal(bridge.snapshot().running, 0);
  } finally {
    await bridge.close();
    store.close();
    temp.cleanup();
  }
});

test("无输出恰好 10 分钟触发空闲超时，迟到的活动不复活计时器", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const temp = temporary(),
    store = new SessionStore(temp.directory);
  let request!: AgentRequest;
  const agent: Agent = {
    async *run(input) {
      request = input;
      await new Promise<void>((resolve) =>
        input.signal.addEventListener("abort", () => resolve(), { once: true }),
      );
      input.signal.throwIfAborted();
    },
  };
  const bridge = new Bridge(
    { codex: agent, cursor: agent },
    store,
    settings,
    logger,
  );
  const output = reply(),
    running = bridge.handle(message("stalled"), output);
  try {
    await turn();
    t.mock.timers.tick(599_999);
    assert.equal(request.signal.aborted, false);
    t.mock.timers.tick(1);
    await running;
    assert.match(output.finals[0]!, /连续 600 秒无输出.*空闲超时/);
    const reason = request.signal.reason;
    request.onActivity?.();
    t.mock.timers.tick(3_600_000);
    assert.equal(request.signal.reason, reason);
    assert.equal(output.finals.length, 1);
  } finally {
    await bridge.close();
    store.close();
    temp.cleanup();
  }
});

test("附件准备也受空闲时限约束，不等待未响应的下载", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const temp = temporary(),
    store = new SessionStore(temp.directory);
  const agent: Agent = {
    async *run() {
      assert.fail("不得启动 CLI");
    },
  };
  const bridge = new Bridge(
    { codex: agent, cursor: agent },
    store,
    settings,
    logger,
  );
  const output = reply(),
    running = bridge.handle(
      message("download"),
      output,
      () => new Promise(() => {}),
    );
  try {
    await turn();
    t.mock.timers.tick(600_000);
    await running;
    assert.match(output.finals[0]!, /空闲超时/);
  } finally {
    await bridge.close();
    store.close();
    temp.cleanup();
  }
});

test("正常完成后清理两类时限，后续活动不会取消已完成请求", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const temp = temporary(),
    store = new SessionStore(temp.directory);
  let request!: AgentRequest;
  const agent: Agent = {
    async *run(input) {
      request = input;
      yield { type: "completed" };
    },
  };
  const bridge = new Bridge(
    { codex: agent, cursor: agent },
    store,
    settings,
    logger,
  );
  try {
    await bridge.handle(message("done"), reply());
    request.onActivity?.();
    t.mock.timers.tick(3_600_000);
    assert.equal(request.signal.aborted, false);
  } finally {
    await bridge.close();
    store.close();
    temp.cleanup();
  }
});

for (const kind of ["idle", "hard", "cancel"] as const) {
  test(`真实 CLI ${kind} 终止会清理进程且保留对应原因`, async () => {
    const temp = temporary(),
      store = new SessionStore(temp.directory);
    const command = executable(
      temp.directory,
      `
      console.log('{"type":"thread.started","thread_id":"test"}');
      ${kind === "hard" ? `setInterval(() => process.stderr.write('active'), 50);` : ""}
      setInterval(() => {}, 1000);
    `,
    );
    const agent = new CliAgent(
      "codex",
      { command, writable: false },
      temp.directory,
    );
    const bridge = new Bridge(
      { codex: agent, cursor: agent },
      store,
      {
        ...settings,
        idleTimeoutMs: 300,
        hardTimeoutMs: 900,
      },
      logger,
    );
    const output = reply(),
      running = bridge.handle(message("test"), output);
    try {
      if (kind === "cancel") {
        await turn();
        await bridge.handle(message("/cancel"), reply());
      }
      await running;
      assert.match(
        output.finals[0]!,
        kind === "idle"
          ? /空闲超时/
          : kind === "hard"
            ? /总时限/
            : /任务已取消/,
      );
      assert.equal(bridge.snapshot().running, 0);
    } finally {
      await bridge.close();
      store.close();
      temp.cleanup();
    }
  });
}

test("真实 CLI 不完整大工具事件的字节持续刷新空闲计时", async () => {
  const temp = temporary(),
    store = new SessionStore(temp.directory);
  const command = executable(
    temp.directory,
    `
    console.log('{"type":"thread.started","thread_id":"test"}');
    process.stdout.write('{"type":"item.completed","item":{"type":"mcp_tool_call","result":"');
    let chunks = 0;
    const interval = setInterval(() => {
      process.stdout.write('x'.repeat(4096));
      if (++chunks === 12) {
        clearInterval(interval);
        console.log('"}}');
        console.log('{"type":"item.completed","item":{"type":"agent_message","text":"完成"}}');
        console.log('{"type":"turn.completed"}');
      }
    }, 80);
  `,
  );
  const agent = new CliAgent(
    "codex",
    { command, writable: false },
    temp.directory,
  );
  const bridge = new Bridge(
    { codex: agent, cursor: agent },
    store,
    {
      ...settings,
      idleTimeoutMs: 400,
      hardTimeoutMs: 5000,
    },
    logger,
  );
  const output = reply();
  try {
    await bridge.handle(message("tool"), output);
    assert.equal(output.finals[0], "完成");
  } finally {
    await bridge.close();
    store.close();
    temp.cleanup();
  }
});
