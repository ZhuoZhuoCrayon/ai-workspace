import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, statSync } from "node:fs";
import type { BaseMessage } from "@wecom/aibot-node-sdk";
import { readWeComInput } from "../src/channels/wecom-input.js";
import { temporary } from "./helpers.js";

test("语音、图文和引用转换为通用输入，附件生成独立安全路径", async () => {
  const temp = temporary();
  const png = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10, 0]);
  const downloader = {
    async downloadFile() {
      return { buffer: png, filename: "../../image.png" };
    },
  };
  try {
    const body = {
      msgtype: "mixed",
      mixed: {
        msg_item: [
          { msgtype: "text", text: { content: "看看图片" } },
          { msgtype: "image", image: { url: "https://example.com/image" } },
        ],
      },
      quote: { msgtype: "text", text: { content: "引用内容" } },
    } as unknown as BaseMessage;
    const input = await readWeComInput(downloader, body, temp.directory);
    assert.match(input.text, /引用内容/);
    assert.match(input.text, /看看图片/);
    assert.equal(input.attachments.length, 1);
    const file = input.attachments[0]!;
    assert(file.path.startsWith(temp.directory));
    assert(!file.path.includes("../"));
    assert.equal(file.mimeType, "image/png");
    assert.equal(statSync(file.path).mode & 0o777, 0o600);
    assert.deepEqual(readFileSync(file.path), png);
    const voice = await readWeComInput(
      downloader,
      {
        msgtype: "voice",
        voice: { content: "语音文本" },
      } as unknown as BaseMessage,
      temp.directory,
    );
    assert.equal(voice.text, "语音文本");
  } finally {
    temp.cleanup();
  }
});

test("附件下载有字节上限并响应取消", async () => {
  const { downloadAttachment } = await import("../src/channels/wecom-input.js");
  const controller = new AbortController();
  const stream = new ReadableStream<Uint8Array>({
    start(source) {
      source.enqueue(new Uint8Array(100));
      source.close();
    },
  });
  await assert.rejects(
    downloadAttachment(
      "https://example.com/file",
      undefined,
      controller.signal,
      10,
      async () => new Response(stream),
    ),
    /大小限制/,
  );
  controller.abort(new Error("cancelled"));
  await assert.rejects(
    downloadAttachment(
      "https://example.com/file",
      undefined,
      controller.signal,
      100,
      async () => new Response("abc"),
    ),
    /cancelled/,
  );
});
