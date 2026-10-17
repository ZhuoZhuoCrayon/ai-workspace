import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";
import { BridgeError } from "../types.js";
import type { Agent, AgentEvent, AgentName, AgentRequest } from "../types.js";
import type { AgentConfig } from "../config.js";
import { AgentProtocol, buildArguments } from "./protocol.js";

export class CliAgent implements Agent {
  constructor(
    private readonly name: AgentName,
    private readonly options: AgentConfig,
    private readonly workspace: string,
  ) {}

  async *run(request: AgentRequest): AsyncGenerator<AgentEvent> {
    request.signal.throwIfAborted();
    const env = { ...process.env };
    for (const key of Object.keys(env)) {
      if (key.startsWith("WECOM_") || key.startsWith("BRIDGE_"))
        delete env[key];
    }
    const child = spawn(
      this.options.command,
      buildArguments(
        this.name,
        { ...this.options, ...(request.model ? { model: request.model } : {}) },
        request.sessionId,
        request.images,
      ),
      {
        cwd: this.workspace,
        env,
        shell: false,
        detached: true,
        stdio: ["pipe", "pipe", "pipe"],
      },
    );
    const closed = new Promise<{ code: number | null; error?: Error }>(
      (resolve) => {
        child.once("error", (error) => resolve({ code: null, error }));
        child.once("close", (code) => resolve({ code }));
      },
    );
    // 标准错误只消费不转发，避免 CLI 日志泄漏环境和文件内容。
    child.stderr.resume();
    child.stdin.on("error", () => {});
    child.stdin.end(request.prompt);
    let cleanup: Promise<void> | undefined;
    const stop = (): Promise<void> => {
      cleanup ??= (async () => {
        const pid = child.pid;
        if (!pid) return;
        const groupExists = (): boolean => {
          try {
            process.kill(-pid, 0);
            return true;
          } catch (error) {
            return (error as NodeJS.ErrnoException).code !== "ESRCH";
          }
        };
        const signalGroup = (signal: NodeJS.Signals): void => {
          try {
            process.kill(-pid, signal);
          } catch (error) {
            if ((error as NodeJS.ErrnoException).code !== "ESRCH") {
              try {
                child.kill(signal);
              } catch {
                /* 进程已退出。 */
              }
            }
          }
        };
        const waitForGroup = async (milliseconds: number): Promise<boolean> => {
          const deadline = Date.now() + milliseconds;
          while (groupExists()) {
            if (Date.now() >= deadline) return false;
            await delay(20);
          }
          return true;
        };
        if (!groupExists()) return;
        signalGroup("SIGTERM");
        if (await waitForGroup(1000)) return;
        signalGroup("SIGKILL");
        // 升级完成后才结束 run，停机调用方可安全退出；僵尸回收不无限延长清理。
        await waitForGroup(500);
      })();
      return cleanup;
    };
    const kill = (): void => {
      void stop();
    };
    request.signal.addEventListener("abort", kill, { once: true });
    if (request.signal.aborted) kill();
    const parser = new AgentProtocol(this.name);
    let buffer = "";
    child.stdout.setEncoding("utf8");
    try {
      for await (const chunk of child.stdout) {
        request.signal.throwIfAborted();
        buffer += chunk;
        let newline: number;
        while ((newline = buffer.indexOf("\n")) >= 0) {
          if (newline > 1_048_576)
            throw new BridgeError("Agent 单条事件超过长度上限。");
          const line = buffer.slice(0, newline).trim();
          buffer = buffer.slice(newline + 1);
          if (line) yield* parser.parse(line);
        }
        if (buffer.length > 1_048_576)
          throw new BridgeError("Agent 单条事件超过长度上限。");
      }
      if (buffer.trim()) yield* parser.parse(buffer.trim());
      const exit = await closed;
      request.signal.throwIfAborted();
      if (exit.error)
        throw new BridgeError(
          `${this.name} 无法启动，请安装对应 CLI，并检查 command 和可执行文件权限。`,
        );
      if (exit.code !== 0)
        throw new BridgeError(
          `${this.name} 退出异常。请先在本机运行 ${this.name === "codex" ? "codex login" : "cursor-agent login"}，并检查模型与权限配置。`,
        );
      if (!parser.completed || !parser.sessionId)
        throw new BridgeError("Agent 未返回完整终态或会话 ID。");
      yield { type: "completed" };
    } finally {
      request.signal.removeEventListener("abort", kill);
      const stopping = stop();
      child.stdout.destroy();
      await Promise.all([closed, stopping]);
    }
  }
}
