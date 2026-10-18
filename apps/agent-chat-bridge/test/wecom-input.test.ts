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

test("文本与 mixed 引用保留正文，移除当前提问的机器人前缀", async () => {
  const temp = temporary();
  const downloader = {
    async downloadFile(): Promise<never> {
      throw new Error("不应下载");
    },
  };
  try {
    for (const quote of [
      {
        msgtype: "text",
        text: { content: "**告警**\n[详情](https://example.com/alert)" },
      },
      {
        msgtype: "mixed",
        mixed: {
          msg_item: [
            {
              msgtype: "text",
              text: { content: "**告警**\n[详情](https://example.com/alert)" },
            },
          ],
        },
      },
    ]) {
      const result = await readWeComInput(
        downloader,
        {
          msgtype: "text",
          text: { content: "@机器人 帮我分析" },
          quote,
        } as unknown as BaseMessage,
        temp.directory,
      );
      assert.match(result.text, /\[引用消息\]\n\*\*告警\*\*/);
      assert.match(result.text, /https:\/\/example.com\/alert/);
      assert(result.text.endsWith("帮我分析"));
      assert(!result.text.includes("@机器人"));
    }
  } finally {
    temp.cleanup();
  }
});

test("真实回调中的占位引用明确标记缺失，保留当前链接且不伪造原文", async () => {
  const temp = temporary();
  const downloader = {
    async downloadFile(): Promise<never> {
      throw new Error("不应下载");
    },
  };
  try {
    for (const quote of [
      { msgtype: "text", text: { content: "[该消息类型暂不能展示]" } },
      { msgtype: "unknown" },
      { msgtype: "text", text: {} },
      { msgtype: "markdown", markdown: { content: "未支持的内容块" } },
    ]) {
      const result = await readWeComInput(
        downloader,
        {
          msgtype: "text",
          text: { content: "@机器人 看 https://example.com/alert" },
          quote,
        } as unknown as BaseMessage,
        temp.directory,
      );
      assert.match(result.text, /引用原文缺失/);
      assert.match(result.text, /不要把旧会话当作引用原文/);
      assert(result.text.endsWith("看 https://example.com/alert"));
      assert(!result.text.includes("[引用消息]\n[该消息类型暂不能展示]"));
    }
  } finally {
    temp.cleanup();
  }
});
