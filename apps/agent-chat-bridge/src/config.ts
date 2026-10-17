import { readFileSync, realpathSync, statSync } from "node:fs";
import { dirname, isAbsolute, resolve } from "node:path";
import { BridgeError, isAgentName } from "./types.js";
import type { AgentName } from "./types.js";

export interface AgentConfig {
  command: string;
  model?: string;
  writable: boolean;
  models?: string[];
}

export interface Config {
  channel: "wecom" | "terminal";
  workspace: string;
  stateDir: string;
  defaultAgent: AgentName;
  maxConcurrent: number;
  requestsPerMinute: number;
  timeoutMs: number;
  healthPort: number;
  agents: Record<AgentName, AgentConfig>;
  wecom: {
    allowedUsers: string[];
    updateIntervalMs: number;
    streamWindowMs: number;
  };
}

function object(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new BridgeError(`${label} 必须是对象。`);
  return value as Record<string, unknown>;
}

function integer(
  value: unknown,
  fallback: number,
  min: number,
  max: number,
  label: string,
): number {
  const number = value ?? fallback;
  if (
    typeof number !== "number" ||
    !Number.isSafeInteger(number) ||
    number < min ||
    number > max
  )
    throw new BridgeError(`${label} 必须是 ${min}～${max} 的整数。`);
  return number;
}

function text(value: unknown, fallback: string, label: string): string {
  const result = value ?? fallback;
  if (typeof result !== "string" || !result.trim() || result.includes("\0"))
    throw new BridgeError(`${label} 必须是非空字符串。`);
  return result;
}

export function loadConfig(file: string): Config {
  const root = dirname(resolve(file));
  const raw = object(JSON.parse(readFileSync(file, "utf8")), "配置");
  const workspace = realpathSync(
    resolve(root, text(raw.workspace, ".", "workspace")),
  );
  if (!statSync(workspace).isDirectory())
    throw new BridgeError("workspace 必须是目录。");
  const defaultAgent = raw.defaultAgent ?? "codex";
  if (!isAgentName(defaultAgent))
    throw new BridgeError("defaultAgent 只能是 codex 或 cursor。");
  const agents = object(raw.agents ?? {}, "agents");
  if (Object.keys(agents).some((name) => !isAgentName(name)))
    throw new BridgeError("agents 仅支持 codex 和 cursor。");
  const parseAgent = (name: AgentName): AgentConfig => {
    const options = object(agents[name] ?? {}, `agents.${name}`);
    if (options.writable !== undefined && typeof options.writable !== "boolean")
      throw new BridgeError("writable 必须是布尔值。");
    let command = text(
      options.command,
      name === "codex" ? "codex" : "cursor-agent",
      "command",
    );
    if (command.includes("/") && !isAbsolute(command))
      command = resolve(root, command);
    const model =
      options.model === undefined
        ? undefined
        : text(options.model, "", "model");
    const models = options.models ?? [];
    if (
      !Array.isArray(models) ||
      models.length > 30 ||
      !models.every(
        (id) =>
          typeof id === "string" &&
          /^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,199}$/.test(id),
      ) ||
      new Set(models).size !== models.length
    )
      throw new BridgeError("models 必须是最多 30 项、不重复的模型 ID 数组。");
    return {
      command,
      writable: options.writable === true,
      ...(model ? { model } : {}),
      models,
    };
  };
  const wecom = object(raw.wecom ?? {}, "wecom");
  const allowedUsers = wecom.allowedUsers ?? [];
  if (
    !Array.isArray(allowedUsers) ||
    !allowedUsers.every(
      (id) => typeof id === "string" && id.trim() && id !== "*",
    )
  )
    throw new BridgeError("allowedUsers 必须是明确的用户 ID 数组。");
  const channel = raw.channel ?? "wecom";
  if (channel !== "wecom" && channel !== "terminal")
    throw new BridgeError("channel 只能是 wecom 或 terminal。");
  return {
    channel,
    workspace,
    stateDir: resolve(root, text(raw.stateDir, ".state", "stateDir")),
    defaultAgent,
    maxConcurrent: integer(raw.maxConcurrent, 4, 1, 32, "maxConcurrent"),
    requestsPerMinute: integer(
      raw.requestsPerMinute,
      10,
      1,
      100,
      "requestsPerMinute",
    ),
    timeoutMs: integer(raw.timeoutMs, 600_000, 1000, 86_400_000, "timeoutMs"),
    healthPort: integer(raw.healthPort, 0, 0, 65535, "healthPort"),
    agents: { codex: parseAgent("codex"), cursor: parseAgent("cursor") },
    wecom: {
      allowedUsers,
      updateIntervalMs: integer(
        wecom.updateIntervalMs,
        1500,
        1000,
        60_000,
        "updateIntervalMs",
      ),
      streamWindowMs: integer(
        wecom.streamWindowMs,
        300_000,
        5000,
        300_000,
        "streamWindowMs",
      ),
    },
  };
}
