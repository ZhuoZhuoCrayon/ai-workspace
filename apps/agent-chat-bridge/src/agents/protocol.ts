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
      ...(options.fullAccess
        ? ["--dangerously-bypass-approvals-and-sandbox"]
        : [
            "-c",
            `sandbox_mode="${options.writable ? "workspace-write" : "read-only"}"`,
          ]),
      "-c",
      'model_reasoning_effort="high"',
      "-c",
      'model_reasoning_summary="auto"',
      "-c",
      'service_tier="default"',
      ...(!options.fullAccess && options.networkAccess !== undefined
        ? [
            "-c",
            `sandbox_workspace_write.network_access=${options.networkAccess}`,
          ]
        : []),
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
    "--stream-partial-output",
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
  private pendingMessage = "";
  private readonly reasoning = new Map<string, string>();
  private cursorThinking = "";
  private partialSeen = false;
  private progressText = "";

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
    let separator = this.text ? "\n\n" : "";
    if (
      this.name === "codex" &&
      ["item.started", "item.updated", "item.completed"].includes(event.type)
    ) {
      const item = record(event.item);
      const active = event.type !== "item.completed";
      if (item.type === "reasoning") {
        if (typeof item.text === "string" && item.text) {
          this.reasoning.set(
            typeof item.id === "string" ? item.id : "current",
            item.text.slice(-4000),
          );
          if (this.reasoning.size > 20)
            this.reasoning.delete(this.reasoning.keys().next().value!);
        }
        this.progressText =
          [...this.reasoning.values()].join("\n\n").slice(-4000) || "正在思考…";
        result.push({ type: "progress", content: this.progressText, active });
      }
      const tools: Record<string, string> = {
        command_execution: "执行命令",
        file_change: "更新文件",
        mcp_tool_call: "调用工具",
        web_search: "搜索资料",
        todo_list: "更新计划",
      };
      if (typeof item.type === "string" && tools[item.type]) {
        if (active && this.pendingMessage) {
          result.push(this.commentary(this.pendingMessage));
          this.pendingMessage = "";
        }
        const status = `${active ? "正在" : "已完成"}${tools[item.type]}。`;
        result.push({
          type: "progress",
          content: `${this.progressText ? this.progressText + "\n\n" : ""}${status}`,
          active: false,
        });
      }
    }
    if (this.name === "cursor" && event.type === "thinking") {
      if (event.subtype === "delta" && typeof event.text === "string") {
        this.cursorThinking = (this.cursorThinking + event.text).slice(-4000);
      }
      this.progressText = this.cursorThinking || "正在思考…";
      result.push({
        type: "progress",
        content: this.progressText,
        active: event.subtype !== "completed",
      });
    }
    if (this.name === "cursor" && event.type === "tool_call") {
      if (event.subtype === "started") {
        if (this.text) result.push(this.commentary(this.text));
        this.text = "";
        this.partialSeen = false;
      }
      result.push({
        type: "progress",
        content: `${this.progressText ? this.progressText + "\n\n" : ""}${event.subtype === "started" ? "正在调用工具。" : "工具执行完成。"}`,
        active: false,
      });
    }
    if (this.name === "codex" && event.type === "item.completed") {
      const item = record(event.item);
      if (item.type === "agent_message" && typeof item.text === "string")
        content = item.text;
    }
    if (this.name === "cursor" && event.type === "assistant") {
      const message = record(event.message);
      if (Array.isArray(message.content)) {
        content = message.content
          .map((part) => record(part))
          .filter(
            (part) => part.type === "text" && typeof part.text === "string",
          )
          .map((part) => part.text)
          .join("");
        const partial =
          event.timestamp_ms !== undefined && event.model_call_id === undefined;
        if (partial) {
          this.partialSeen = true;
          separator = "";
        } else if (this.partialSeen || (content && this.text.endsWith(content)))
          content = undefined;
      }
    }
    if (content) {
      if (this.name === "codex") {
        if (this.pendingMessage)
          result.push(this.commentary(this.pendingMessage));
        this.pendingMessage = content;
        if (content.length > this.maxTextLength)
          throw new BridgeError("Agent 回复超过长度上限，任务已终止。");
      } else {
        this.text += separator + content;
        this.checkLength();
      }
    }
    if (
      this.name === "cursor" &&
      event.type === "result" &&
      (typeof event.result === "string" || this.text)
    ) {
      const raw = typeof event.result === "string" ? event.result : "";
      const normalize = (text: string) => text.replace(/\s+/g, "");
      if (!this.text || (raw && !normalize(raw).endsWith(normalize(this.text))))
        this.text = raw || this.text;
      this.checkLength();
      result.push({ type: "text", content: this.text });
    }
    if (
      this.name === "codex" &&
      event.type === "turn.completed" &&
      this.pendingMessage
    ) {
      this.text = this.pendingMessage;
      this.pendingMessage = "";
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

  private commentary(content: string): AgentEvent {
    this.progressText =
      `${this.progressText ? this.progressText + "\n\n" : ""}${content}`.slice(
        -4000,
      );
    return { type: "progress", content: this.progressText, active: false };
  }
}
