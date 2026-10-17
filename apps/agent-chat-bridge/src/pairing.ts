import { randomBytes, timingSafeEqual } from "node:crypto";
import type { IncomingMessage } from "./types.js";

interface PairingOptions {
  /** 必须同步持久化用户，写入失败时抛出异常。 */
  saveUser(id: string): void;
  accountId?: string;
  code?: string;
  expiresMs?: number;
  now?: () => number;
}

export type PairingResult =
  { kind: "ignored" } | { kind: "paired" | "expired" | "failed"; text: string };

const ATTEMPT_WINDOW_MS = 60_000;
const MAX_FAILED_ATTEMPTS = 5;

export class PairingGate {
  readonly code: string;
  private readonly now: () => number;
  private readonly expiresAt: number;
  private attemptWindowStartedAt: number;
  private failedAttempts = 0;
  private pairedUser: string | undefined;

  constructor(private readonly options: PairingOptions) {
    const code = options.code ?? randomBytes(4).toString("hex");
    if (!/^[a-f0-9]{8}$/i.test(code)) {
      throw new Error("配对码必须是 8 位十六进制字符。");
    }
    const expiresMs = options.expiresMs ?? 10 * 60_000;
    if (!Number.isSafeInteger(expiresMs) || expiresMs <= 0) {
      throw new Error("配对有效期必须是正整数。");
    }
    this.code = code.toLowerCase();
    this.now = options.now ?? Date.now;
    const startedAt = this.now();
    this.expiresAt = startedAt + expiresMs;
    this.attemptWindowStartedAt = startedAt;
  }

  handle(message: IncomingMessage): PairingResult {
    if (
      message.channel !== "wecom" ||
      !message.userId ||
      message.userId.length > 500 ||
      message.conversationId !== `single:${message.userId}` ||
      (this.options.accountId !== undefined &&
        message.accountId !== this.options.accountId) ||
      message.attachments?.length
    ) {
      return { kind: "ignored" };
    }
    const text = message.text.trim();
    if (!/^\/pair(?:\s|$)/.test(text)) return { kind: "ignored" };
    const candidate = text.match(/^\/pair ([a-f0-9]{8})$/i)?.[1];
    const matches =
      candidate !== undefined &&
      timingSafeEqual(
        Buffer.from(candidate.toLowerCase()),
        Buffer.from(this.code),
      );

    if (this.pairedUser !== undefined) {
      return matches && message.userId === this.pairedUser
        ? { kind: "paired", text: "当前用户已绑定，可以直接发送问题。" }
        : { kind: "ignored" };
    }

    const now = this.now();
    if (now >= this.expiresAt) {
      return {
        kind: "expired",
        text: "配对码已过期，请在本机重新启动服务生成新码。",
      };
    }
    if (now - this.attemptWindowStartedAt >= ATTEMPT_WINDOW_MS) {
      this.failedAttempts = 0;
      this.attemptWindowStartedAt = now;
    }
    if (this.failedAttempts >= MAX_FAILED_ATTEMPTS) {
      return { kind: "failed", text: "配对尝试过于频繁，请稍后重试。" };
    }
    if (!matches) {
      this.failedAttempts++;
      return {
        kind: "failed",
        text: "配对指令无效，请核对本机显示的配对指令。",
      };
    }

    try {
      this.options.saveUser(message.userId);
    } catch {
      return { kind: "failed", text: "绑定保存失败，请在本机检查配置后重试。" };
    }
    this.pairedUser = message.userId;
    return { kind: "paired", text: "绑定成功，可以直接发送问题。" };
  }
}
