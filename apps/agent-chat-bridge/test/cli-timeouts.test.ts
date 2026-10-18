import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as delay } from "node:timers/promises";
import { executable, temporary } from "./helpers.js";

for (const kind of ["idle", "hard", "active"] as const) {
  test(
    `完整 CLI 加载自定义 ${kind} 时限，探活报告生效配置`,
    { timeout: 15_000 },
    async () => {
      const temp = temporary();
      const reservation = createServer();
      await new Promise<void>((resolve) =>
        reservation.listen(0, "127.0.0.1", resolve),
      );
      const address = reservation.address();
      assert(address && typeof address !== "string");
      const port = address.port;
      await new Promise<void>((resolve) => reservation.close(() => resolve()));
      const idleTimeoutMs = kind === "hard" ? 5000 : 1000;
      const hardTimeoutMs = kind === "hard" ? 1000 : 5000;
      const command = executable(
        temp.directory,
        `
      if (process.argv.includes('--version')) { console.log('test-cli'); process.exit(0); }
      console.log('{"type":"thread.started","thread_id":"configured"}');
      ${
        kind === "idle"
          ? "setInterval(() => {}, 1000);"
          : `
        let ticks = 0;
        const timer = setInterval(() => {
          process.stderr.write('tool activity');
          if (++ticks === 8 && ${kind === "active"}) {
            clearInterval(timer);
            console.log('{"type":"item.completed","item":{"type":"agent_message","text":"READY"}}');
            console.log('{"type":"turn.completed"}');
          }
        }, 200);
      `
      }
    `,
      );
      const configFile = join(temp.directory, "config.json");
      writeFileSync(
        configFile,
        JSON.stringify({
          channel: "terminal",
          workspace: temp.directory,
          stateDir: "state",
          healthPort: port,
          idleTimeoutMs,
          hardTimeoutMs,
          agents: { codex: { command } },
        }),
      );
      const child = spawn(
        process.execPath,
        [
          "--import",
          "tsx",
          fileURLToPath(new URL("../src/cli.ts", import.meta.url)),
          "--config",
          configFile,
        ],
        {
          cwd: fileURLToPath(new URL("..", import.meta.url)),
          stdio: ["pipe", "pipe", "pipe"],
        },
      );
      let output = "",
        errors = "";
      child.stdout.on("data", (chunk) => {
        output += chunk;
      });
      child.stderr.on("data", (chunk) => {
        errors += chunk;
      });
      const closed = new Promise<number | null>((resolve, reject) => {
        child.once("error", reject);
        child.once("close", resolve);
      });
      try {
        let state:
          | { timeouts?: { idleTimeoutMs: number; hardTimeoutMs: number } }
          | undefined;
        for (let attempt = 0; attempt < 100; attempt++) {
          try {
            state = await (
              await fetch(`http://127.0.0.1:${port}/metrics`, {
                signal: AbortSignal.timeout(500),
              })
            ).json();
            break;
          } catch {
            await delay(25);
          }
        }
        assert.deepEqual(
          state?.timeouts,
          { idleTimeoutMs, hardTimeoutMs },
          errors,
        );
        child.stdin.end("test configured timeout\n");
        assert.equal(await closed, 0, errors);
        if (kind === "active") assert.equal(output.trim(), "READY");
        else
          assert.match(
            output,
            kind === "idle" ? /连续 1 秒无输出.*空闲超时/ : /总时限（1 秒）/,
          );
      } finally {
        child.kill("SIGTERM");
        await closed;
        temp.cleanup();
      }
    },
  );
}
