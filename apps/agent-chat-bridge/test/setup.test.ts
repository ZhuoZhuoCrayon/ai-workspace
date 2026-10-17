import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import {
  existsSync,
  readdirSync,
  readFileSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { join } from "node:path";
import { initialize, savePairedUser } from "../src/setup.js";
import { loadConfig } from "../src/config.js";
import { temporary } from "./helpers.js";

function scripted(values: string[]) {
  const questions: Array<{ label: string; secret: boolean }> = [];
  let closed = false;
  return {
    questions,
    get closed() {
      return closed;
    },
    async ask(label: string, secret = false) {
      questions.push({ label, secret });
      const value = values.shift();
      assert.notEqual(value, undefined);
      return value!;
    },
    close() {
      closed = true;
    },
  };
}

test("向导生成可直接启动的配置和私有凭据，不要求 userid", async () => {
  const temp = temporary(),
    prompt = scripted(["", "", "", "", "test-bot", "test-only-secret"]);
  try {
    const file = await initialize(temp.directory, prompt);
    const config = loadConfig(file);
    assert.equal(config.channel, "wecom");
    assert.equal(config.defaultAgent, "codex");
    assert.deepEqual(config.wecom.allowedUsers, []);
    assert.equal(config.agents.codex.writable, false);
    assert.equal(statSync(file).mode & 0o777, 0o600);
    assert.equal(statSync(join(temp.directory, ".env")).mode & 0o777, 0o600);
    assert(prompt.questions.at(-1)?.secret);
    assert(prompt.closed);
    savePairedUser(file, "user-1");
    savePairedUser(file, "user-1");
    assert.deepEqual(loadConfig(file).wecom.allowedUsers, ["user-1"]);
    assert(!readFileSync(file, "utf8").includes("test-only-secret"));
    const existing = scripted([]);
    await initialize(temp.directory, existing);
    assert(existing.closed);
    assert.deepEqual(existing.questions, []);
  } finally {
    temp.cleanup();
  }
});

test("终端模式跳过机器人凭据，可显式选择可写 Cursor", async () => {
  const temp = temporary(),
    prompt = scripted(["terminal", "", "cursor", "yes"]);
  try {
    const file = await initialize(temp.directory, prompt);
    const config = loadConfig(file);
    assert.equal(config.channel, "terminal");
    assert.equal(config.defaultAgent, "cursor");
    assert(config.agents.cursor.writable);
    assert.equal(prompt.questions.length, 4);
  } finally {
    temp.cleanup();
  }
});

test("凭据经 env 编码保持引号和反斜线，已有凭据可以补全初始化", async () => {
  const { parseEnv } = await import("node:util");
  for (const secret of ["back\\slash", 'double"quote', `both'"quotes`]) {
    const temp = temporary();
    try {
      await initialize(
        temp.directory,
        scripted(["", "", "", "", "bot-id", secret]),
      );
      assert.equal(
        parseEnv(readFileSync(join(temp.directory, ".env"), "utf8"))
          .WECOM_BOT_SECRET,
        secret,
      );
    } finally {
      temp.cleanup();
    }
  }
  const temp = temporary();
  try {
    writeFileSync(
      join(temp.directory, ".env"),
      "WECOM_BOT_ID=existing\nWECOM_BOT_SECRET=existing-placeholder\n",
      { mode: 0o600 },
    );
    const prompt = scripted(["", "", "", ""]);
    const file = await initialize(temp.directory, prompt);
    assert.equal(loadConfig(file).channel, "wecom");
    assert.equal(prompt.questions.length, 4);
    assert.match(
      readFileSync(join(temp.directory, ".env"), "utf8"),
      /existing-placeholder/,
    );
  } finally {
    temp.cleanup();
  }
});

test("配置部分写入失败不留下残缺文件，可重试且保留原有凭据", () => {
  const temp = temporary();
  try {
    execFileSync(
      process.execPath,
      [
        "--import",
        "tsx",
        "--input-type=module",
        "-e",
        `
import fs from 'node:fs';
import assert from 'node:assert/strict';
import { syncBuiltinESMExports } from 'node:module';
import { join } from 'node:path';
const { initialize } = await import(${JSON.stringify(new URL("../src/setup.ts", import.meta.url).href)});
const directory = ${JSON.stringify(temp.directory)};
const file = join(directory, 'bridge.local.json');
const envFile = join(directory, '.env');
const originalWrite = fs.writeFileSync;
const prompt = (existing) => {
  const values = existing ? ['', '', '', ''] : ['', '', '', '', 'bot', 'secret'];
  return { async ask() { assert(values.length); return values.shift(); }, close() {} };
};
for (const existing of [false, true]) {
  const originalEnv = 'WECOM_BOT_ID=existing\\nWECOM_BOT_SECRET=existing-secret\\n';
  if (existing) originalWrite(envFile, originalEnv, { mode: 0o600 });
  fs.writeFileSync = function(path, value, options) {
    if (String(path).includes('/.setup-')) {
      originalWrite(path, '{', options);
      throw Object.assign(new Error('simulated partial write'), { code: 'ENOSPC' });
    }
    return originalWrite(path, value, options);
  };
  syncBuiltinESMExports();
  try {
    await assert.rejects(initialize(directory, prompt(existing)), /配置写入失败/);
  } finally {
    fs.writeFileSync = originalWrite;
    syncBuiltinESMExports();
  }
  assert(!fs.existsSync(file));
  assert(!fs.readdirSync(directory).some(name => name.startsWith('.setup-')));
  assert.equal(fs.existsSync(envFile), existing);
  if (existing) assert.equal(fs.readFileSync(envFile, 'utf8'), originalEnv);
  await initialize(directory, prompt(existing));
  assert.equal(JSON.parse(fs.readFileSync(file, 'utf8')).channel, 'wecom');
  fs.unlinkSync(file);
  fs.unlinkSync(envFile);
}
`,
      ],
      { stdio: "pipe" },
    );
  } finally {
    temp.cleanup();
  }
});

test("向导期间出现的配置不会被覆盖，失败后清理本次凭据和临时文件", async () => {
  const temp = temporary();
  const file = join(temp.directory, "bridge.local.json");
  const original = '{"existing":true}\n';
  const prompt = scripted(["", "", "", "", "bot", "secret"]);
  try {
    await assert.rejects(
      initialize(temp.directory, {
        async ask(label, secret) {
          const value = await prompt.ask(label, secret);
          if (secret) writeFileSync(file, original, { flag: "wx" });
          return value;
        },
        close: () => prompt.close(),
      }),
      /配置写入失败/,
    );
    assert.equal(readFileSync(file, "utf8"), original);
    assert(!existsSync(join(temp.directory, ".env")));
    assert.deepEqual(readdirSync(temp.directory), ["bridge.local.json"]);
    assert(prompt.closed);
  } finally {
    temp.cleanup();
  }
});
