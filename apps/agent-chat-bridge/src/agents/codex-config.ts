import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { BridgeError } from "../types.js";

// 让 Codex 自己解析用户、项目和 profile 配置，仅保留本次覆盖需要的一个字段。
export async function readDeveloperInstructions(
  command: string,
  cwd: string,
  env: NodeJS.ProcessEnv,
  signal: AbortSignal,
  onActivity?: () => void,
): Promise<string> {
  const child = spawn(command, ["app-server", "--listen", "stdio://"], {
    cwd,
    env,
    signal,
    stdio: ["pipe", "pipe", "ignore"],
  });
  child.stdin.on("error", () => {});
  const lines = createInterface({ input: child.stdout });
  const closed = new Promise<void>((resolve) =>
    child.once("close", () => resolve()),
  );
  child.on("error", () => lines.close());
  const timeout = setTimeout(() => child.kill("SIGKILL"), 5000);
  const send = (id: number, method: string, params: object) =>
    child.stdin.write(JSON.stringify({ id, method, params }) + "\n");
  try {
    send(1, "initialize", {
      clientInfo: { name: "agent-chat-bridge", version: "1" },
    });
    for await (const line of lines) {
      onActivity?.();
      const response = JSON.parse(line);
      if (response.error) break;
      if (response.id === 1)
        send(2, "config/read", { cwd, includeLayers: false });
      if (response.id === 2) {
        const config = response.result?.config;
        if (!config || typeof config !== "object") break;
        const value = config.developer_instructions;
        if (value == null || typeof value === "string") return value ?? "";
        break;
      }
    }
  } catch {
    // 不向聊天转发可能包含本机配置的协议原文。
  } finally {
    clearTimeout(timeout);
    lines.close();
    child.stdin.end();
    child.kill("SIGKILL");
    await closed;
  }
  signal.throwIfAborted();
  throw new BridgeError(
    "无法读取 Codex developer_instructions，请检查 CLI 是否支持 app-server config/read。",
  );
}
