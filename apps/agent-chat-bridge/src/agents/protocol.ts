import { BridgeError } from "../types.js";
import type { AgentEvent, AgentName } from "../types.js";
import type { AgentConfig } from "../config.js";

export function buildArguments(
  name: AgentName,
  options: AgentConfig,
  sessionId?: string,
  images: string[] = [],
): string[] {
  if (sessionId && !/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,199}$/.test(sessionId))
    throw new BridgeError("Agent 会话 ID 无效。");
  const model = options.model ? ["--model", options.model] : [];
  if (name === "codex") {
    return [
      "exec",
      "--json",
      "--skip-git-repo-check",
      "--color",
      "never",
      "-c",
      'approval_policy="never"',
      "-c",
      `sandbox_mode="${options.writable ? "workspace-write" : "read-only"}"`,
      ...model,
      ...images.flatMap((image) => ["--image", image]),
      ...(sessionId ? ["resume", sessionId] : []),
      "-",
    ];
  }
  return [
    "--print",
    "--trust",
    "--output-format",
    "stream-json",
    ...(options.writable ? ["--force"] : ["--mode", "ask"]),
    ...model,
    ...(sessionId ? ["--resume", sessionId] : []),
  ];
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export class AgentProtocol {
  completed = false;
  sessionId: string | undefined;
  private text = "";

  constructor(
    private readonly name: AgentName,
    private readonly maxTextLength = 100_000,
  ) {}

  parse(line: string): AgentEvent[] {
    let value: unknown;
    try {
      value = JSON.parse(line);
    } catch {
      throw new BridgeError("Agent 输出了无效 JSON，任务已终止。");
    }
    const event = record(value);
    if (typeof event.type !== "string")
      throw new BridgeError("Agent 事件缺少类型。");
    const result: AgentEvent[] = [];
    const id =
      this.name === "codex" && event.type === "thread.started"
        ? event.thread_id
        : this.name === "cursor"
          ? event.session_id
          : undefined;
    if (id !== undefined && id !== this.sessionId) {
      if (
        typeof id !== "string" ||
        !/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,199}$/.test(id)
      )
        throw new BridgeError("Agent 输出的会话 ID 无效。");
      if (this.sessionId)
        throw new BridgeError("Agent 在任务中切换了会话 ID。");
      this.sessionId = id;
      result.push({ type: "session", id });
    }
    if (
      event.type === "turn.failed" ||
      event.type === "error" ||
      (event.type === "result" &&
        (event.is_error === true || event.subtype !== "success"))
    ) {
      throw new BridgeError(
        "Agent 报告任务失败，请在本机检查 CLI 认证和配置。",
      );
    }
    let content: string | undefined;
    if (this.name === "codex" && event.type === "item.completed") {
      const item = record(event.item);
      if (item.type === "agent_message" && typeof item.text === "string")
        content = item.text;
    }
    if (this.name === "cursor" && event.type === "assistant") {
      const message = record(event.message);
      if (Array.isArray(message.content))
        content = message.content
          .map((part) => record(part))
          .filter(
            (part) => part.type === "text" && typeof part.text === "string",
          )
          .map((part) => part.text)
          .join("");
    }
    if (content) {
      this.text += (this.text ? "\n\n" : "") + content;
      this.checkLength();
      result.push({ type: "text", content: this.text });
    }
    if (
      this.name === "cursor" &&
      event.type === "result" &&
      typeof event.result === "string"
    ) {
      this.text = event.result;
      this.checkLength();
      result.push({ type: "text", content: this.text });
    }
    if (
      (this.name === "codex" && event.type === "turn.completed") ||
      (this.name === "cursor" && event.type === "result")
    )
      this.completed = true;
    return result;
  }

  private checkLength(): void {
    if (this.text.length > this.maxTextLength)
      throw new BridgeError("Agent 回复超过长度上限，任务已终止。");
  }
}
