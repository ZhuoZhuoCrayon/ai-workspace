export const AGENT_NAMES = ["codex", "cursor"] as const;
export type AgentName = (typeof AGENT_NAMES)[number];

export function isAgentName(value: unknown): value is AgentName {
  return value === "codex" || value === "cursor";
}

export interface IncomingMessage {
  channel: string;
  accountId: string;
  conversationId: string;
  userId: string;
  messageId: string;
  text: string;
  attachments?: Attachment[];
}

export interface Attachment {
  path: string;
  name: string;
  mimeType: string;
}

export interface Reply {
  update(content: string, progress?: Progress): Promise<void>;
  finish(content: string, progress?: Progress): Promise<void>;
  select?(content: string, choices: ReplyChoice[]): Promise<void>;
}

export interface Progress {
  content: string;
  active: boolean;
}

export interface ReplyChoice {
  label: string;
  command: string;
}

export interface AgentRequest {
  prompt: string;
  sessionId?: string;
  model?: string;
  images?: string[];
  signal: AbortSignal;
}

export type AgentEvent =
  | { type: "session"; id: string }
  | { type: "text"; content: string }
  | ({ type: "progress" } & Progress)
  | { type: "completed" };

export interface Agent {
  run(request: AgentRequest): AsyncIterable<AgentEvent>;
}

export interface Conversation {
  selectedAgent: AgentName;
  sessions: Partial<Record<AgentName, string>>;
  history?: Partial<Record<AgentName, SessionEntry[]>>;
  models?: Partial<Record<AgentName, string>>;
  updatedAt: number;
}

export interface SessionEntry {
  id: string;
  title: string;
  updatedAt: number;
}

export interface Logger {
  info(message: string): void;
  error(message: string): void;
}

export class BridgeError extends Error {}
