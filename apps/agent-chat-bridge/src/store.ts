import { createHash, randomUUID } from "node:crypto";
import {
  chmodSync,
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { join } from "node:path";
import { BridgeError, isAgentName } from "./types.js";
import type {
  AgentName,
  AgentPreference,
  Conversation,
  IncomingMessage,
} from "./types.js";

export function conversationKey(
  message: IncomingMessage,
  workspace = "",
): string {
  return createHash("sha256")
    .update(
      JSON.stringify([
        workspace,
        message.channel,
        message.accountId,
        message.conversationId,
        message.userId,
      ]),
    )
    .digest("hex");
}

export class SessionStore {
  private readonly records = new Map<string, Conversation>();
  private preference: AgentPreference | undefined;
  private readonly file: string;
  private readonly lock: string;
  private closed = false;

  constructor(
    directory: string,
    private readonly retentionMs = 7 * 24 * 60 * 60 * 1000,
    private readonly maxSessions = 1000,
  ) {
    mkdirSync(directory, { recursive: true, mode: 0o700 });
    chmodSync(directory, 0o700);
    this.file = join(directory, "sessions.json");
    this.lock = join(directory, "bridge.lock");
    try {
      writeFileSync(this.lock, String(process.pid), {
        flag: "wx",
        mode: 0o600,
      });
    } catch {
      throw new BridgeError(
        "状态目录已被锁定，请检查 bridge.lock 对应进程，确认停止后再移除锁文件。",
      );
    }
    try {
      this.load();
    } catch (error) {
      this.close();
      throw error;
    }
  }

  private load(): void {
    if (!existsSync(this.file)) return;
    const data: unknown = JSON.parse(readFileSync(this.file, "utf8"));
    if (
      !data ||
      typeof data !== "object" ||
      !("version" in data) ||
      data.version !== 1 ||
      !("sessions" in data) ||
      !Array.isArray(data.sessions)
    ) {
      throw new BridgeError("会话文件格式无效，请备份后修复，避免丢失上下文。");
    }
    for (const entry of data.sessions) {
      const [key, value] = Array.isArray(entry) ? entry : [];
      if (
        typeof key !== "string" ||
        !/^[a-f0-9]{64}$/.test(key) ||
        !value ||
        !isAgentName(value.selectedAgent) ||
        typeof value.updatedAt !== "number" ||
        !Number.isFinite(value.updatedAt) ||
        !value.sessions ||
        typeof value.sessions !== "object" ||
        Array.isArray(value.sessions)
      ) {
        throw new BridgeError("会话文件包含无效记录。");
      }
      const sessions: Conversation["sessions"] = {};
      for (const [name, id] of Object.entries(value.sessions)) {
        if (
          !isAgentName(name) ||
          typeof id !== "string" ||
          !/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,199}$/.test(id)
        ) {
          throw new BridgeError("会话文件包含无效 Agent ID。");
        }
        sessions[name] = id;
      }
      const history: NonNullable<Conversation["history"]> = {};
      if (
        value.history !== undefined &&
        (!value.history ||
          typeof value.history !== "object" ||
          Array.isArray(value.history))
      )
        throw new BridgeError("会话历史格式无效。");
      for (const [name, entries] of Object.entries(value.history ?? {})) {
        if (
          !isAgentName(name) ||
          !Array.isArray(entries) ||
          entries.length > 10 ||
          !entries.every(
            (entry) =>
              entry &&
              typeof entry.id === "string" &&
              /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,199}$/.test(entry.id) &&
              typeof entry.title === "string" &&
              entry.title.length <= 60 &&
              typeof entry.updatedAt === "number" &&
              Number.isFinite(entry.updatedAt),
          )
        )
          throw new BridgeError("会话历史记录无效。");
        history[name] = entries.filter(
          (entry) => Date.now() - entry.updatedAt < this.retentionMs,
        );
      }
      this.records.set(key, {
        selectedAgent: value.selectedAgent,
        sessions,
        history,
        models: readModels(value.models),
        updatedAt: value.updatedAt,
      });
    }
    if (this.records.size > this.maxSessions)
      throw new BridgeError("会话数量超过上限，请清理状态目录。");
    const stored = Object.prototype.hasOwnProperty.call(data, "preference")
      ? readPreference((data as { preference?: unknown }).preference)
      : undefined;
    this.adoptPreference(stored);
  }

  get(key: string): Conversation | undefined {
    const value = this.records.get(key);
    if (!value) return undefined;
    const clone = structuredClone(value);
    for (const name of ["codex", "cursor"] as const) {
      if (clone.history?.[name])
        clone.history[name] = clone.history[name]!.filter(
          (entry) => Date.now() - entry.updatedAt < this.retentionMs,
        );
    }
    return clone;
  }

  getPreference(): AgentPreference | undefined {
    return this.preference ? structuredClone(this.preference) : undefined;
  }

  put(key: string, value: Conversation, preference?: AgentPreference): void {
    if (this.closed) throw new BridgeError("会话存储已关闭。");
    if (!this.records.has(key) && this.records.size >= this.maxSessions)
      throw new BridgeError("会话数量达到上限。");
    const previous = this.records.get(key);
    const previousPreference = this.preference;
    this.records.set(key, structuredClone(value));
    if (preference) this.preference = structuredClone(preference);
    const temporary = `${this.file}.${randomUUID()}.tmp`;
    try {
      writeFileSync(temporary, JSON.stringify(this.snapshot()), {
        mode: 0o600,
        flag: "wx",
      });
      renameSync(temporary, this.file);
    } catch (error) {
      if (previous) this.records.set(key, previous);
      else this.records.delete(key);
      this.preference = previousPreference;
      if (existsSync(temporary)) unlinkSync(temporary);
      throw error;
    }
  }

  private snapshot(): {
    version: 1;
    sessions: [string, Conversation][];
    preference?: AgentPreference;
  } {
    return {
      version: 1,
      sessions: [...this.records],
      ...(this.preference ? { preference: this.preference } : {}),
    };
  }

  private adoptPreference(stored: AgentPreference | undefined): void {
    if (stored) {
      this.preference = stored;
      return;
    }
    const ordered = [...this.records.values()].sort(
      (left, right) => left.updatedAt - right.updatedAt,
    );
    const latest = ordered.at(-1);
    if (!latest) return;
    const models: Partial<Record<AgentName, string>> = {};
    for (const record of ordered) Object.assign(models, record.models);
    this.preference = {
      selectedAgent: latest.selectedAgent,
      models,
      updatedAt: latest.updatedAt,
    };
  }

  close(): void {
    if (this.closed) return;
    this.closed = true;
    unlinkSync(this.lock);
  }
}

function readModels(value: unknown): Partial<Record<AgentName, string>> {
  if (value === undefined) return {};
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new BridgeError("模型偏好格式无效。");
  const models: Partial<Record<AgentName, string>> = {};
  for (const [name, id] of Object.entries(value)) {
    if (
      !isAgentName(name) ||
      typeof id !== "string" ||
      !/^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,199}$/.test(id)
    )
      throw new BridgeError("模型偏好无效。");
    models[name] = id;
  }
  return models;
}

function readPreference(value: unknown): AgentPreference | undefined {
  if (value === undefined) return undefined;
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new BridgeError("模型偏好格式无效。");
  const record = value as Record<string, unknown>;
  if (
    !isAgentName(record.selectedAgent) ||
    typeof record.updatedAt !== "number" ||
    !Number.isFinite(record.updatedAt)
  )
    throw new BridgeError("模型偏好格式无效。");
  return {
    selectedAgent: record.selectedAgent,
    models: readModels(record.models),
    updatedAt: record.updatedAt,
  };
}
