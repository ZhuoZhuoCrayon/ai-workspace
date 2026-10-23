import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { temporary } from "./helpers.js";

test("企业微信启动在缺少独立执行账号时拒绝，不能回落到控制账号", () => {
  const temp = temporary();
  try {
    const file = join(temp.directory, "config.json");
    const original = JSON.stringify({
      channel: "wecom",
      workspace: temp.directory,
      wecom: { allowedUsers: ["owner"], adminUsers: ["owner"] },
    });
    writeFileSync(file, original, { mode: 0o600 });
    const result = spawnSync(
      process.execPath,
      [
        "--import",
        "tsx",
        fileURLToPath(new URL("../src/cli.ts", import.meta.url)),
        "--config",
        file,
      ],
      {
        encoding: "utf8",
        timeout: 10000,
        env: {
          ...process.env,
          WECOM_BOT_ID: "test-bot",
          WECOM_BOT_SECRET: "MUST-NOT-BE-LOGGED",
        },
      },
    );
    assert.equal(result.status, 1);
    assert.match(result.stderr, /必须配置独立 execution 账号/);
    assert(!result.stderr.includes("MUST-NOT-BE-LOGGED"));
    assert.equal(readFileSync(file, "utf8"), original);
    assert(!existsSync(join(temp.directory, ".state", "bridge.lock")));
  } finally {
    temp.cleanup();
  }
});
