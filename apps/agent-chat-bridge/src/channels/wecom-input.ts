import { decryptFile } from "@wecom/aibot-node-sdk";
import { randomUUID } from "node:crypto";
import {
  mkdirSync,
  writeFileSync,
  readdirSync,
  lstatSync,
  unlinkSync,
} from "node:fs";
import { join, resolve } from "node:path";
import type { BaseMessage, WSClient } from "@wecom/aibot-node-sdk";
import type { Attachment } from "../types.js";
import { BridgeError } from "../types.js";
import { stripBotMention } from "./text.js";

export function imageType(
  buffer: Buffer,
): { mimeType: string; extension: string } | undefined {
  if (
    buffer.length >= 8 &&
    buffer.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
  )
    return { mimeType: "image/png", extension: "png" };
  if (
    buffer.length >= 3 &&
    buffer[0] === 255 &&
    buffer[1] === 216 &&
    buffer[2] === 255
  )
    return { mimeType: "image/jpeg", extension: "jpg" };
  if (
    buffer.length >= 12 &&
    buffer.toString("ascii", 0, 4) === "RIFF" &&
    buffer.toString("ascii", 8, 12) === "WEBP"
  )
    return { mimeType: "image/webp", extension: "webp" };
  if (buffer.length >= 6 && /^GIF8[79]a$/.test(buffer.toString("ascii", 0, 6)))
    return { mimeType: "image/gif", extension: "gif" };
  return undefined;
}

interface MediaReference {
  url: string;
  aeskey?: string;
  image: boolean;
}

export async function readWeComInput(
  client: Pick<WSClient, "downloadFile">,
  body: BaseMessage,
  directory: string,
  signal?: AbortSignal,
): Promise<{ text: string; attachments: Attachment[] }> {
  const references: MediaReference[] = [];
  const segments: string[] = [];
  let quoteUnavailable = false;
  const collect = (
    part: Record<string, any>,
    quoted: boolean,
    depth = 0,
  ): void => {
    if (depth > 3 || references.length > 5)
      throw new BridgeError("消息附件结构超出限制。");
    const text =
      part.msgtype === "voice"
        ? part.voice?.content
        : part.msgtype === "text"
          ? part.text?.content
          : undefined;
    if (typeof text === "string" && text.trim()) {
      if (quoted && /^[\[【]?该消息类型暂不能展示[\]】]?$/.test(text.trim()))
        quoteUnavailable = true;
      else
        segments.push(
          quoted ? `[引用消息]\n${text}` : stripBotMention(text).text,
        );
    }
    if (part.msgtype === "mixed") {
      for (const item of part.mixed?.msg_item ?? [])
        collect(item, quoted, depth + 1);
    }
    if (part.msgtype === "image" || part.msgtype === "file") {
      const media = part[part.msgtype];
      if (
        !media ||
        typeof media.url !== "string" ||
        !media.url.startsWith("https://")
      )
        throw new BridgeError("附件下载地址无效。");
      references.push({
        url: media.url,
        ...(typeof media.aeskey === "string" ? { aeskey: media.aeskey } : {}),
        image: part.msgtype === "image",
      });
    }
  };
  if (body.quote) {
    collect(body.quote, true);
    if (!segments.length && !references.length) quoteUnavailable = true;
  }
  collect(body, false);
  if (references.length > 5)
    throw new BridgeError("单条消息最多包含 5 个附件。");
  const root = resolve(directory);
  const attachments: Attachment[] = [];
  if (references.length) {
    mkdirSync(root, { recursive: true, mode: 0o700 });
    for (const entry of readdirSync(root, { withFileTypes: true })) {
      if (!entry.isFile() || !/^[a-f0-9-]{36}\.[a-z0-9]+$/.test(entry.name))
        continue;
      const file = join(root, entry.name);
      if (Date.now() - lstatSync(file).mtimeMs > 7 * 86_400_000)
        unlinkSync(file);
    }
  }
  try {
    for (const media of references) {
      const { buffer, filename } = await client.downloadFile(
        media.url,
        media.aeskey,
      );
      if (
        !buffer.length ||
        buffer.length > (media.image ? 10 : 20) * 1024 * 1024
      )
        throw new BridgeError("附件为空或超过大小限制。");
      signal?.throwIfAborted();
      const type = imageType(buffer);
      if (media.image && !type)
        throw new BridgeError(
          "图片格式不受支持，请发送 PNG、JPEG、WebP 或 GIF。",
        );
      const extension =
        type?.extension ??
        (filename?.match(/\.([a-zA-Z0-9]{1,10})$/)?.[1]?.toLowerCase() ||
          "bin");
      const path = join(root, `${randomUUID()}.${extension}`);
      writeFileSync(path, buffer, { flag: "wx", mode: 0o600 });
      attachments.push({
        path,
        name: filename?.slice(0, 200) || `attachment.${extension}`,
        mimeType: type?.mimeType ?? "application/octet-stream",
      });
    }
  } catch (error) {
    for (const attachment of attachments) unlinkSync(attachment.path);
    throw error;
  }
  if (quoteUnavailable)
    segments.unshift(
      "[引用原文缺失或不完整]\n仅依据本条可见内容回答，不要把旧会话当作引用原文。需要原文时，请用户复制正文或提供源链接。",
    );
  return {
    text:
      segments.join("\n\n") || (attachments.length ? "请查看附件并回答。" : ""),
    attachments,
  };
}

export async function downloadAttachment(
  url: string,
  aesKey: string | undefined,
  signal: AbortSignal,
  maxBytes = 20 * 1024 * 1024,
  fetcher: typeof fetch = fetch,
): Promise<{ buffer: Buffer; filename?: string }> {
  const deadline = AbortSignal.any([signal, AbortSignal.timeout(15_000)]);
  const response = await fetcher(url, { signal: deadline, redirect: "error" });
  const limit = maxBytes + 32;
  if (!response.ok || !response.body) throw new BridgeError("附件下载失败。");
  if (Number(response.headers.get("content-length")) > limit) {
    await response.body.cancel();
    throw new BridgeError("附件超过大小限制。");
  }
  const reader = response.body.getReader();
  const chunks: Buffer[] = [];
  let total = 0;
  try {
    while (true) {
      const part = await reader.read();
      deadline.throwIfAborted();
      if (part.done) break;
      total += part.value.byteLength;
      if (total > limit) throw new BridgeError("附件超过大小限制。");
      chunks.push(Buffer.from(part.value));
    }
  } finally {
    await reader.cancel().catch(() => {});
  }
  const raw = Buffer.concat(chunks, total);
  const buffer = aesKey ? decryptFile(raw, aesKey) : raw;
  if (buffer.length > maxBytes) throw new BridgeError("附件超过大小限制。");
  const disposition = response.headers.get("content-disposition") ?? "";
  const encoded =
    disposition.match(/filename\*=UTF-8''([^;\s]+)/i)?.[1] ??
    disposition.match(/filename="?([^";]+)"?/i)?.[1];
  let filename: string | undefined;
  try {
    filename = encoded ? decodeURIComponent(encoded).slice(0, 200) : undefined;
  } catch {}
  return { buffer, ...(filename ? { filename } : {}) };
}
