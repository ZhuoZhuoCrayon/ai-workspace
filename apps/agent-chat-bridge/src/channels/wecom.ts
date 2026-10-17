import { readWeComInput, downloadAttachment } from "./wecom-input.js";
import { extractImages } from "./outbound-images.js";
import { stripBotMention, splitMarkdownByBytes } from "./text.js";
import { randomUUID } from "node:crypto";
import { setTimeout as delay } from "node:timers/promises";
import type {
  WSClient,
  TextMessage,
  BaseMessage,
  WsFrame,
  WsFrameHeaders,
} from "@wecom/aibot-node-sdk";
import type { PairingGate } from "../pairing.js";
import type { Bridge } from "../bridge.js";
import type { IncomingMessage, Logger, Reply } from "../types.js";

type Sender = Pick<WSClient, "replyStream" | "sendMessage"> &
  Partial<Pick<WSClient, "uploadMedia">>;

export function splitUtf8(text: string, bytes: number): string[] {
  const parts: string[] = [];
  let part = "";
  let size = 0;
  for (const character of text) {
    const length = Buffer.byteLength(character);
    if (size + length > bytes && part) {
      parts.push(part);
      part = "";
      size = 0;
    }
    part += character;
    size += length;
  }
  if (part) parts.push(part);
  return parts;
}

export function normalizeWeCom(
  frame: WsFrame<BaseMessage>,
  botId: string,
): IncomingMessage | undefined {
  const body = frame.body;
  if (
    !body ||
    body.aibotid !== botId ||
    typeof body.msgid !== "string" ||
    !body.msgid ||
    typeof body.from?.userid !== "string" ||
    !body.from.userid ||
    !frame.headers?.req_id
  )
    return;
  if (body.chattype !== "single" && body.chattype !== "group") return;
  if (
    body.chattype === "group" &&
    (typeof body.chatid !== "string" || !body.chatid)
  )
    return;
  return {
    channel: "wecom",
    accountId: botId,
    conversationId:
      body.chattype === "group"
        ? `group:${body.chatid}`
        : `single:${body.from.userid}`,
    userId: body.from.userid,
    messageId: body.msgid,
    text:
      typeof body.text?.content === "string"
        ? stripBotMention(body.text.content).text
        : "",
  };
}

export class DeliveryQueue {
  private tail = Promise.resolve();
  private pending = 0;
  private lastSent = 0;

  constructor(private readonly spacingMs = 2100) {}

  send(action: () => Promise<unknown>): Promise<void> {
    if (this.pending >= 64)
      return Promise.reject(new Error("平台发送队列已满。"));
    this.pending++;
    const result = this.tail
      .then(async () => {
        const wait = this.spacingMs - (Date.now() - this.lastSent);
        if (wait > 0) await delay(wait);
        this.lastSent = Date.now();
        await action();
      })
      .finally(() => {
        this.pending--;
      });
    this.tail = result.catch(() => {});
    return result;
  }
}

export class WeComReply implements Reply {
  private readonly streamId = randomUUID();
  private latest = "";
  private lastUpdate = 0;
  private updateTimer: NodeJS.Timeout | undefined;
  private windowTimer: NodeJS.Timeout | undefined;
  private operations = Promise.resolve();
  private proactive = false;
  private finished = false;

  constructor(
    private readonly client: Sender,
    private readonly queue: DeliveryQueue,
    private readonly frame: WsFrameHeaders,
    private readonly target: string,
    private readonly logger: Logger,
    private readonly intervalMs = 2500,
    private readonly windowMs = 280_000,
    private readonly workspace?: string,
  ) {}

  async update(content: string): Promise<void> {
    if (this.finished || this.proactive) return;
    this.latest = content;
    if (!this.windowTimer) {
      this.windowTimer = setTimeout(() => {
        this.clearUpdateTimer();
        void this.enqueue(async () => {
          await this.stream("任务仍在处理，完成后会推送结果。", true);
          this.proactive = true;
        });
      }, this.windowMs);
      this.windowTimer.unref();
    }
    if (!this.lastUpdate) {
      await this.enqueue(() => this.stream(content, false));
    } else if (!this.updateTimer) {
      this.updateTimer = setTimeout(
        () => {
          this.updateTimer = undefined;
          void this.enqueue(async () => {
            if (!this.proactive && !this.finished)
              await this.stream(this.latest, false);
          });
        },
        Math.max(0, this.intervalMs - (Date.now() - this.lastUpdate)),
      );
      this.updateTimer.unref();
    }
  }

  async finish(content: string): Promise<void> {
    if (this.finished) return;
    this.finished = true;
    this.clearUpdateTimer();
    clearTimeout(this.windowTimer);
    await this.operations;
    const extracted =
      this.workspace && this.client.uploadMedia
        ? extractImages(content, this.workspace)
        : { text: content, images: [] };
    await this.finishText(
      extracted.text ||
        (extracted.images.length ? "图片结果如下。" : "任务完成。"),
    );
    for (const image of extracted.images) {
      try {
        const media = await this.client.uploadMedia!(image.buffer, {
          type: "image",
          filename: image.filename,
        });
        await this.queue.send(() =>
          this.client.sendMessage(this.target, {
            msgtype: "image",
            image: { media_id: media.media_id },
          }),
        );
      } catch {
        this.logger.error("企业微信图片结果交付失败。");
        await this.queue.send(() =>
          this.client.sendMessage(this.target, {
            msgtype: "markdown",
            markdown: { content: "图片结果发送失败，请稍后重试。" },
          }),
        );
      }
    }
  }

  private async finishText(content: string): Promise<void> {
    if (!this.proactive && Buffer.byteLength(content) <= 19_900) {
      await this.stream(content, true);
      if (!this.proactive) return;
    } else if (!this.proactive) {
      await this.stream("任务完成，结果将分段发送。", true);
      this.proactive = true;
    }
    for (const part of splitMarkdownByBytes(content, 4000)) {
      await this.queue.send(() =>
        this.client.sendMessage(this.target, {
          msgtype: "markdown",
          markdown: { content: part },
        }),
      );
    }
  }

  private enqueue(action: () => Promise<void>): Promise<void> {
    this.operations = this.operations.then(action).catch(() => {
      this.proactive = true;
      this.logger.error("企业微信流式回复失败，终态改用主动消息。");
    });
    return this.operations;
  }

  private async stream(content: string, finish: boolean): Promise<void> {
    const preview = splitUtf8(content, 19_900)[0] ?? "处理中。";
    try {
      await this.queue.send(() =>
        this.client.replyStream(this.frame, this.streamId, preview, finish),
      );
      this.lastUpdate = Date.now();
    } catch {
      this.proactive = true;
      this.logger.error("企业微信流式回复失败，终态改用主动消息。");
    }
  }

  private clearUpdateTimer(): void {
    clearTimeout(this.updateTimer);
    this.updateTimer = undefined;
  }
}

export function connectWeCom(
  client: WSClient,
  bridge: Bridge,
  botId: string,
  logger: Logger,
  onFatal: () => void,
  options: {
    updateIntervalMs: number;
    streamWindowMs: number;
    attachmentDir?: string;
    deliveryQueue?: DeliveryQueue;
    workspace?: string;
    pairing?: PairingGate;
  },
): Promise<void> {
  const queue = options.deliveryQueue ?? new DeliveryQueue();
  client.on("message", (frame) => {
    const message = normalizeWeCom(frame, botId);
    if (!message) return;
    const target =
      frame.body!.chattype === "group" ? frame.body!.chatid! : message.userId;
    const reply = new WeComReply(
      client,
      queue,
      frame,
      target,
      logger,
      options.updateIntervalMs,
      options.streamWindowMs,
      options.workspace,
    );
    if (
      frame.body!.msgtype === "text" &&
      !frame.body!.quote &&
      /^\/pair(?:\s|$)/.test(message.text)
    ) {
      const pairing = options.pairing?.handle(message);
      if (pairing && pairing.kind !== "ignored")
        void reply
          .finish(pairing.text)
          .catch(() => logger.error("配对结果未能交付。"));
      else if (bridge.accepts(message))
        void reply
          .finish("机器人已完成配对，可以直接发送问题。")
          .catch(() => logger.error("配对提示未能交付。"));
      return;
    }
    if (!bridge.accepts(message)) return;
    if (frame.body!.msgtype === "text" && !frame.body!.quote) {
      void bridge
        .handle(message, reply)
        .catch(() => logger.error("企业微信消息未能交付。"));
      return;
    }
    void bridge
      .handle(message, reply, async (signal) => {
        if (
          !["text", "voice", "mixed", "image", "file"].includes(
            frame.body!.msgtype,
          )
        )
          throw new Error("不支持的消息类型");
        const input = await readWeComInput(
          { downloadFile: (url, key) => downloadAttachment(url, key, signal) },
          frame.body!,
          options.attachmentDir ?? ".state/attachments",
          signal,
        );
        return { ...input, text: stripBotMention(input.text).text };
      })
      .catch(() => logger.error("企业微信消息处理或交付失败。"));
  });
  client.on("event.enter_chat", (frame) => {
    const message = normalizeWeCom(frame as WsFrame<BaseMessage>, botId);
    if (!message || !bridge.accepts(message)) return;
    void client
      .replyWelcome(frame, {
        msgtype: "text",
        text: {
          content:
            "直接发送问题即可开始，使用 /agent codex 或 /agent cursor 切换执行器，/help 查看命令。",
        },
      })
      .catch(() => logger.error("企业微信欢迎消息发送失败。"));
  });
  client.on("reconnecting", () =>
    logger.info("企业微信连接断开，SDK 正在重连。"),
  );
  client.on("event.disconnected_event", () => {
    logger.error("机器人连接被其他实例替换，服务停止。");
    onFatal();
  });
  return new Promise((resolve, reject) => {
    let ready = false;
    const timer = setTimeout(
      () => reject(new Error("企业微信认证超时。")),
      30_000,
    );
    client.on("authenticated", () => {
      ready = true;
      clearTimeout(timer);
      logger.info("企业微信连接已认证。");
      resolve();
    });
    client.on("error", (error: Error & { code?: string }) => {
      logger.error("企业微信连接错误，请检查网络、机器人凭据和权限。");
      if (
        error.code === "WS_AUTH_FAILURE_EXHAUSTED" ||
        error.code === "WS_RECONNECT_EXHAUSTED"
      ) {
        clearTimeout(timer);
        if (ready) onFatal();
        else reject(new Error("企业微信连接或认证重试次数已耗尽。"));
      }
    });
    try {
      client.connect();
    } catch {
      clearTimeout(timer);
      reject(new Error("企业微信连接启动失败。"));
    }
  });
}
