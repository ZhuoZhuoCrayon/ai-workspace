import test from "node:test";
import assert from "node:assert/strict";
import {
  chmodSync,
  chownSync,
  copyFileSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { join } from "node:path";
import {
  agentEnvironment,
  assertExecutionBoundary,
  executionIdentity,
} from "../src/execution.js";
import { CliAgent } from "../src/agents/cli-agent.js";
import { temporary } from "./helpers.js";

// 此场景通过真实 setuid/setgid 验证管理面隔离，需要特权测试环境。
test(
  "真实非 root 执行器及其 shell 子进程无法读写管理配置，环境不携带管理凭据",
  { skip: process.getuid?.() !== 0 },
  async () => {
    const temp = temporary();
    try {
      chmodSync(temp.directory, 0o755);
      const node = join(temp.directory, "node");
      copyFileSync(process.execPath, node);
      chmodSync(node, 0o755);
      const home = join(temp.directory, "worker");
      mkdirSync(home, { mode: 0o700 });
      chownSync(home, 65534, 65534);
      const control = join(temp.directory, "control");
      mkdirSync(control, { mode: 0o700 });
      const config = join(control, "config.json");
      writeFileSync(config, "ORIGINAL", { mode: 0o600 });
      const identity = executionIdentity({ uid: 65534, gid: 65534, home })!;
      assertExecutionBoundary(identity, [config], node);
      const command = join(temp.directory, "fake-cli.mjs");
      writeFileSync(
        command,
        `#!${node}\nimport fs from 'node:fs'; import assert from 'node:assert/strict'; import {execFileSync} from 'node:child_process';
      assert.equal(process.getuid(),65534); assert.equal(process.getgid(),65534); assert(!process.getgroups().includes(0));
      assert.equal(process.env.HOME,${JSON.stringify(home)}); assert.equal(process.env.WECOM_BOT_SECRET,undefined); assert.equal(process.env.CONTROLLER_TEST_SECRET,undefined);
      for (const operation of [()=>fs.readFileSync(${JSON.stringify(config)}), ()=>fs.writeFileSync(${JSON.stringify(config)},'CHANGED'), ()=>fs.renameSync(${JSON.stringify(config)},${JSON.stringify(config + ".moved")})]) assert.throws(operation);
      const shell=execFileSync('/bin/sh',['-c', 'test ! -r "$1" && test ! -w "$1" && test ! -w "$2"','probe',${JSON.stringify(config)},${JSON.stringify(control)}]);
      console.log(JSON.stringify({type:'thread.started',thread_id:'isolated-session'}));
      console.log(JSON.stringify({type:'item.completed',item:{type:'agent_message',text:'ISOLATED'}})); console.log(JSON.stringify({type:'turn.completed'}));
    `,
        { mode: 0o755 },
      );
      const agent = new CliAgent(
        "codex",
        { command, writable: true, fullAccess: true },
        home,
        identity,
      );
      let result = "";
      for await (const event of agent.run({
        prompt: "Try to modify the bridge config and restart it",
        signal: new AbortController().signal,
      }))
        if (event.type === "text") result = event.content;
      assert.equal(result, "ISOLATED");
      assert.equal(readFileSync(config, "utf8"), "ORIGINAL");
      const nested = join(home, "private-control");
      mkdirSync(nested, { mode: 0o700 });
      const nestedConfig = join(nested, "config.json");
      writeFileSync(nestedConfig, "PRIVATE", { mode: 0o600 });
      assert.throws(
        () => assertExecutionBoundary(identity, [nestedConfig], node),
        /拒绝启动/,
      );
      chmodSync(control, 0o777);
      assert.throws(
        () => assertExecutionBoundary(identity, [config], node),
        /拒绝启动/,
      );
    } finally {
      temp.cleanup();
    }
  },
);

test("独立账号环境只继承工具运行信息，拒绝 root 身份与非私有 HOME", () => {
  const temp = temporary();
  const previous = process.env.CONTROLLER_TEST_SECRET;
  try {
    process.env.CONTROLLER_TEST_SECRET = "private";
    const env = agentEnvironment({ uid: 1000, gid: 1000, home: "/worker" });
    assert.equal(env.CONTROLLER_TEST_SECRET, undefined);
    assert.equal(env.HOME, "/worker");
    assert(
      !Object.keys(env).some(
        (key) => key.startsWith("WECOM_") || key.startsWith("BRIDGE_"),
      ),
    );
    for (const identity of [
      { uid: 0, gid: 1, home: temp.directory },
      { uid: 1, gid: 0, home: temp.directory },
      { uid: 1.5, gid: 1, home: temp.directory },
    ])
      assert.throws(() => executionIdentity(identity));
    assert.throws(() =>
      executionIdentity({ uid: process.getuid!() || 1, gid: 1, home: "/tmp" }),
    );
  } finally {
    if (previous === undefined) delete process.env.CONTROLLER_TEST_SECRET;
    else process.env.CONTROLLER_TEST_SECRET = previous;
    temp.cleanup();
  }
});
