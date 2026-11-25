import { createDecipheriv, randomUUID } from "node:crypto";
import {
  mkdirSync,
  renameSync,
  readdirSync,
  lstatSync,
  unlinkSync,
} from "node:fs";
import { open, type FileHandle } from "node:fs/promises";
import { join, resolve } from "node:path";
import type { BaseMessage } from "@wecom/aibot-node-sdk";
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

// 企业微信《接收消息》对 file 回调规定的单文件上限。
const maxFileBytes = 100 * 1024 * 1024;

function* messageParts(root: Record<string, any>) {
  const pending = [root];
  while (pending.length) {
    const part = pending.pop()!;
    if (part.msgtype !== "mixed") {
      yield part;
      continue;
    }
    const items = part.mixed?.msg_item ?? [];
    for (let i = items.length - 1; i >= 0; i--) pending.push(items[i]);
  }
}

export async function readWeComInput(
  body: BaseMessage,
  directory: string,
  signal: AbortSignal,
  fetcher: typeof fetch = fetch,
): Promise<{ text: string; attachments: Attachment[] }> {
  const references: MediaReference[] = [];
  const segments: string[] = [];
  let quoteUnavailable = false;
  const collect = (root: Record<string, any>, quoted: boolean): void => {
    for (const part of messageParts(root)) {
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
    }
  };
  if (body.quote) {
    collect(body.quote, true);
    if (!segments.length && !references.length) quoteUnavailable = true;
  }
  collect(body, false);
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
      attachments.push(await saveAttachment(media, root, signal, fetcher));
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

async function saveAttachment(
  media: MediaReference,
  root: string,
  signal: AbortSignal,
  fetcher: typeof fetch,
): Promise<Attachment> {
  signal.throwIfAborted();
  const response = await fetcher(media.url, { signal, redirect: "error" });
  if (!response.ok || !response.body) {
    await response.body?.cancel();
    throw new BridgeError("附件下载失败。");
  }
  const base = join(root, randomUUID());
  const partial = base + ".part";
  const reader = response.body.getReader();
  try {
    const file = await open(partial, "wx+", 0o600);
    try {
      const type = await writeMedia(
        file,
        reader,
        media,
        response.headers,
        signal,
      ).finally(() => file.close());
      signal.throwIfAborted();
      const filename = responseFilename(response);
      const extension =
        type?.extension ??
        (filename?.match(/\.([a-zA-Z0-9]{1,10})$/)?.[1]?.toLowerCase() ||
          "bin");
      const path = base + "." + extension;
      renameSync(partial, path);
      return {
        path,
        name: filename || `attachment.${extension}`,
        mimeType: type?.mimeType ?? "application/octet-stream",
      };
    } catch (error) {
      unlinkSync(partial);
      throw error;
    }
  } finally {
    await reader.cancel().catch(() => {});
  }
}

async function writeMedia(
  file: FileHandle,
  reader: ReadableStreamDefaultReader<Uint8Array>,
  media: MediaReference,
  headers: Headers,
  signal: AbortSignal,
) {
  const maxWireBytes = maxFileBytes + (media.aeskey ? 32 : 0);
  const checkSize = (size: number, limit: number) => {
    if (!media.image && size > limit)
      throw new BridgeError("单个文件超过企微文件回调的 100 MB 上限。");
  };
  checkSize(Number(headers.get("content-length")), maxWireBytes);
  const key = media.aeskey ? Buffer.from(media.aeskey, "base64") : undefined;
  const decipher =
    key &&
    createDecipheriv("aes-256-cbc", key, key.subarray(0, 16)).setAutoPadding(
      false,
    );
  let size = 0;
  while (true) {
    const part = await reader.read();
    signal.throwIfAborted();
    if (part.done) break;
    size += part.value.byteLength;
    checkSize(size, maxWireBytes);
    await file.writeFile(decipher ? decipher.update(part.value) : part.value);
  }
  if (decipher) {
    await file.writeFile(decipher.final());
    // 企微按 32 字节填充，Node 的自动去填充只支持 AES 的 16 字节块。
    const tail = Buffer.alloc(Math.min(32, size));
    await file.read(tail, 0, tail.length, size - tail.length);
    const pad = tail.at(-1) ?? 0;
    if (
      !pad ||
      pad > tail.length ||
      !tail.subarray(-pad).every((byte) => byte === pad)
    )
      throw new BridgeError("附件解密失败，请重新发送。");
    size -= pad;
    await file.truncate(size);
  }
  if (!size) throw new BridgeError("附件为空。");
  checkSize(size, maxFileBytes);
  const header = Buffer.alloc(Math.min(12, size));
  await file.read(header, 0, header.length, 0);
  const type = imageType(header);
  if (media.image && !type)
    throw new BridgeError("图片格式不受支持，请发送 PNG、JPEG、WebP 或 GIF。");
  return type;
}

function responseFilename(response: Response): string | undefined {
  const disposition = response.headers.get("content-disposition") ?? "";
  const encoded =
    disposition.match(/filename\*=UTF-8''([^;\s]+)/i)?.[1] ??
    disposition.match(/filename="?([^";]+)"?/i)?.[1];
  let filename: string | undefined;
  try {
    filename = encoded ? decodeURIComponent(encoded).slice(0, 200) : undefined;
  } catch {}
  return filename;
}
