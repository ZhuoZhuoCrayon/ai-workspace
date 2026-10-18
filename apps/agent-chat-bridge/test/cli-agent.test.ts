import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync, realpathSync } from "node:fs";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { CliAgent } from "../src/agents/cli-agent.js";
import { executable, temporary } from "./helpers.js";

const drain = async (
  agent: CliAgent,
  signal = new AbortController().signal,
  sessionId?: string,
) => {
  const events = [];
  for await (const event of agent.run({
    prompt: "--flag; $(touch untrusted)",
    signal,
    ...(sessionId ? { sessionId } : {}),
  }))
    events.push(event);
  return events;
};

test("真实子进程边界：stdin 原文、恢复 ID、凭据过滤和终态", async () => {
  const temp = temporary(),
    file = join(temp.directory, "observed.json");
  const command = executable(
    temp.directory,
    `import fs from 'node:fs';
 let prompt='';for await(const chunk of process.stdin)prompt+=chunk;
 fs.writeFileSync(${JSON.stringify(file)},JSON.stringify({args:process.argv.slice(2),prompt,hasSecret:!!process.env.WECOM_BOT_SECRET,cwd:process.cwd()}));
 console.log(JSON.stringify({type:'thread.started',thread_id:'thread-1'}));
 console.log(JSON.stringify({type:'item.completed',item:{type:'agent_message',text:'完成'}}));
 console.log(JSON.stringify({type:'turn.completed'}));`,
  );
  const previous = process.env.WECOM_BOT_SECRET;
  process.env.WECOM_BOT_SECRET = "test-only-secret";
  try {
    const events = await drain(
      new CliAgent("codex", { command, writable: false }, temp.directory),
      undefined,
      "thread-1",
    );
    assert.equal(events.at(-1)?.type, "completed");
    const observed = JSON.parse(readFileSync(file, "utf8"));
    assert.equal(observed.prompt, "--flag; $(touch untrusted)");
    assert.equal(observed.hasSecret, false);
    assert.equal(observed.cwd, realpathSync(temp.directory));
    assert.deepEqual(observed.args.slice(-3), ["resume", "thread-1", "-"]);
    assert(!existsSync(join(temp.directory, "untrusted")));
  } finally {
    if (previous === undefined) delete process.env.WECOM_BOT_SECRET;
    else process.env.WECOM_BOT_SECRET = previous;
    temp.cleanup();
  }
});

test("正常终态之后非零退出、缺终态、无效 JSON 和缺可执行文件均失败", async () => {
  const temp = temporary();
  try {
    for (const source of [
      `console.log('{"type":"thread.started","thread_id":"thread-1"}');console.log('{"type":"turn.completed"}');process.exitCode=2;`,
      `console.log('{"type":"thread.started","thread_id":"thread-1"}');`,
      `console.log('invalid json');`,
    ])
      await assert.rejects(
        drain(
          new CliAgent(
            "codex",
            { command: executable(temp.directory, source), writable: false },
            temp.directory,
          ),
        ),
      );
    await assert.rejects(
      drain(
        new CliAgent(
          "cursor",
          { command: join(temp.directory, "missing"), writable: false },
          temp.directory,
        ),
      ),
    );
  } finally {
    temp.cleanup();
  }
});

test("子进程发出超过旧上限的工具结果后，仍交付最终答复", async () => {
  const temp = temporary();
  try {
    const command = executable(
      temp.directory,
      `
console.log(JSON.stringify({type:'thread.started',thread_id:'large-tool'}));
console.log(JSON.stringify({type:'item.completed',item:{type:'mcp_tool_call',id:'tool-1',result:{content:[{type:'text',text:'工具原文😀'.repeat(500000)}]}}}));
console.log(JSON.stringify({type:'item.completed',item:{type:'agent_message',text:'大型工具调用后正常完成'}}));
process.stdout.write(JSON.stringify({type:'turn.completed'}));
`,
    );
    const events = await drain(
      new CliAgent("codex", { command, writable: false }, temp.directory),
    );
    assert.equal(events.at(-1)?.type, "completed");
    assert(
      events.some(
        (event) =>
          event.type === "text" && event.content === "大型工具调用后正常完成",
      ),
    );
  } finally {
    temp.cleanup();
  }
});

test("取消会清理忽略 SIGTERM 的进程组", async () => {
  const temp = temporary(),
    pidFile = join(temp.directory, "pids");
  const command = executable(
    temp.directory,
    `import {spawn} from 'node:child_process';import fs from 'node:fs';
 process.on('SIGTERM',()=>{});const child=spawn(process.execPath,['-e','process.on("SIGTERM",()=>{});setInterval(()=>{},1000)'],{stdio:'ignore'});
 fs.writeFileSync(${JSON.stringify(pidFile)},JSON.stringify([process.pid,child.pid]));setInterval(()=>{},1000);`,
  );
  const controller = new AbortController();
  try {
    const task = drain(
      new CliAgent("codex", { command, writable: false }, temp.directory),
      controller.signal,
    );
    const rejection = assert.rejects(task);
    for (let i = 0; i < 100 && !existsSync(pidFile); i++) await delay(10);
    assert(existsSync(pidFile));
    await delay(100);
    controller.abort();
    await rejection;
    const pids = JSON.parse(readFileSync(pidFile, "utf8")) as number[];
    await delay(100);
    for (const pid of pids) assert.throws(() => process.kill(pid, 0));
  } finally {
    controller.abort();
    temp.cleanup();
  }
});

test("直接进程先退出时，run 仍等待忽略 SIGTERM 的后代清理", async () => {
  const temp = temporary();
  const pidFile = join(temp.directory, "pids");
  const readyFile = join(temp.directory, "descendant-ready");
  const descendant = `process.on('SIGTERM',()=>{});require('node:fs').writeFileSync(${JSON.stringify(readyFile)},'ready');setInterval(()=>{},1000);`;
  const command = executable(
    temp.directory,
    `
import {spawn} from 'node:child_process';
import fs from 'node:fs';
const child=spawn(process.execPath,['-e',${JSON.stringify(descendant)}],{stdio:'ignore'});
fs.writeFileSync(${JSON.stringify(pidFile)},JSON.stringify([process.pid,child.pid]));
setInterval(()=>{},1000);
`,
  );
  const controller = new AbortController();
  let pids: number[] | undefined;
  const task = drain(
    new CliAgent("codex", { command, writable: false }, temp.directory),
    controller.signal,
  );
  const rejected = assert.rejects(task);
  try {
    for (let index = 0; index < 200 && !existsSync(readyFile); index++)
      await delay(10);
    assert(existsSync(readyFile));
    pids = JSON.parse(readFileSync(pidFile, "utf8")) as number[];
    controller.abort();
    await rejected;
    assert.throws(() => process.kill(pids![1]!, 0));
  } finally {
    controller.abort();
    if (pids) {
      try {
        process.kill(-pids[0]!, "SIGKILL");
      } catch {
        /* 已清理。 */
      }
    }
    await task.catch(() => {});
    temp.cleanup();
  }
});
