import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { SessionStore, conversationKey } from "../src/store.js";
import { loadConfig } from "../src/config.js";
import { temporary, message } from "./helpers.js";

test("状态目录锁定、原子持久化、权限和损坏检测", () => {
  const temp = temporary();
  let store = new SessionStore(temp.directory);
  try {
    assert.throws(() => new SessionStore(temp.directory), /锁定/);
    const key = conversationKey(message("hi"));
    store.put(key, {
      selectedAgent: "cursor",
      sessions: { cursor: "cursor-session" },
      updatedAt: Date.now(),
    });
    assert.equal(
      statSync(join(temp.directory, "sessions.json")).mode & 0o777,
      0o600,
    );
    assert.equal(statSync(temp.directory).mode & 0o777, 0o700);
    const clone = store.get(key)!;
    clone.selectedAgent = "codex";
    assert.equal(store.get(key)!.selectedAgent, "cursor");
    store.close();
    store = new SessionStore(temp.directory);
    assert.equal(store.get(key)!.sessions.cursor, "cursor-session");
    store.close();
    writeFileSync(join(temp.directory, "sessions.json"), "invalid");
    assert.throws(() => new SessionStore(temp.directory));
    writeFileSync(
      join(temp.directory, "sessions.json"),
      JSON.stringify({ version: 1, sessions: [] }),
    );
    store = new SessionStore(temp.directory);
  } finally {
    store.close();
    temp.cleanup();
  }
});

test("配置拒绝旧执行器和错误类型，相对路径按配置目录解析", () => {
  const temp = temporary(),
    file = join(temp.directory, "config.json");
  try {
    writeFileSync(
      file,
      JSON.stringify({
        workspace: ".",
        agents: { codex: { writable: false } },
      }),
    );
    const cfg = loadConfig(file);
    assert.equal(
      cfg.workspace.endsWith(temp.directory.split("/").at(-1)!),
      true,
    );
    assert.equal(cfg.defaultAgent, "codex");
    assert.equal(cfg.agents.cursor.writable, false);
    for (const invalid of [
      { defaultAgent: "claude" },
      { agents: { claude: {} } },
      { agents: { cursor: { writable: "yes" } } },
      { timeoutMs: 0 },
      { wecom: { allowedUsers: ["*"] } },
      { agents: { codex: { models: ["--bad"] } } },
    ]) {
      writeFileSync(file, JSON.stringify(invalid));
      assert.throws(() => loadConfig(file));
    }
  } finally {
    temp.cleanup();
  }
});

test("workspace 参与会话身份，切换工作目录不复用会话", () => {
  const input = message("hello");
  assert.notEqual(
    conversationKey(input, "/repo/a"),
    conversationKey(input, "/repo/b"),
  );
});

test("当前会话与模型闲置不丢失，只有过期归档被过滤", () => {
  const temp = temporary();
  let store = new SessionStore(temp.directory, 100);
  const key = conversationKey(message("hi")),
    past = Date.now() - 1000;
  try {
    store.put(key, {
      selectedAgent: "cursor",
      sessions: { cursor: "cursor-current" },
      models: { cursor: "model-a" },
      history: {
        cursor: [{ id: "old-session", title: "old", updatedAt: past }],
      },
      updatedAt: past,
    });
    assert.deepEqual(store.get(key)?.history?.cursor, []);
    store.close();
    store = new SessionStore(temp.directory, 100);
    assert.equal(store.get(key)?.selectedAgent, "cursor");
    assert.equal(store.get(key)?.sessions.cursor, "cursor-current");
    assert.equal(store.get(key)?.models?.cursor, "model-a");
    assert.deepEqual(store.get(key)?.history?.cursor, []);
  } finally {
    store.close();
    temp.cleanup();
  }
});
