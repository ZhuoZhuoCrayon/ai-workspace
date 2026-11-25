import test from "node:test";
import assert from "node:assert/strict";
import { createCipheriv, randomBytes } from "node:crypto";
import { readFileSync, readdirSync, statSync } from "node:fs";
import type { BaseMessage } from "@wecom/aibot-node-sdk";
import { readWeComInput } from "../src/channels/wecom-input.js";
import { temporary } from "./helpers.js";

const png = Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10, 0]);
const signal = new AbortController().signal;
const fileMessage = {
  msgtype: "file",
  file: { url: "https://example.com/file" },
};
const noDownload = async (): Promise<never> => {
  throw new Error("不应下载");
};

test("多图引用和本条消息按回调顺序交付所有图片", async () => {
  const temp = temporary();
  const downloads: string[] = [];
  const urls = Array.from({ length: 41 }, (_, i) => `https://example.com/${i}`);
  const images = urls.map((url) => ({ msgtype: "image", image: { url } }));
  const message = {
    msgtype: "mixed",
    mixed: {
      msg_item: [
        { msgtype: "text", text: { content: "请按图拆分" } },
        ...images.slice(-1),
      ],
    },
    quote: {
      msgtype: "mixed",
      mixed: {
        msg_item: [
          { msgtype: "text", text: { content: "第三个问题" } },
          ...images.slice(0, -1),
        ],
      },
    },
  };
  try {
    const result = await readWeComInput(
      message as unknown as BaseMessage,
      temp.directory,
      signal,
      async (url) => {
        downloads.push(String(url));
        return new Response(png);
      },
    );
    assert.equal(result.text, "[引用消息]\n第三个问题\n\n请按图拆分");
    assert.equal(result.attachments.length, urls.length);
    assert.deepEqual(downloads, urls);
  } finally {
    temp.cleanup();
  }
});

test("100 MB 文件连同大于 10 MB 的引用图片均可接收", async () => {
  const temp = temporary();
  const message = {
    ...fileMessage,
    quote: { msgtype: "image", image: { url: "https://example.com/image" } },
  };
  const block = new Uint8Array(1024 * 1024);
  block.set(png);
  try {
    const result = await readWeComInput(
      message as unknown as BaseMessage,
      temp.directory,
      signal,
      async (url) => {
        let remaining = String(url).endsWith("/image") ? 11 : 100;
        return new Response(
          new ReadableStream({
            pull(controller) {
              if (remaining-- > 0) controller.enqueue(block);
              else controller.close();
            },
          }),
        );
      },
    );
    assert.deepEqual(
      result.attachments.map((item) => statSync(item.path).size),
      [11, 100].map((n) => n * block.length),
    );
  } finally {
    temp.cleanup();
  }
});
test("语音、图文和引用转换为通用输入，附件生成独立安全路径", async () => {
  const temp = temporary();
  const png = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10, 0]);
  const downloader = async () =>
    new Response(png, {
      headers: {
        "content-disposition": 'attachment; filename="../../image.png"',
      },
    });
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
    const input = await readWeComInput(
      body,
      temp.directory,
      signal,
      downloader,
    );
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
      {
        msgtype: "voice",
        voice: { content: "语音文本" },
      } as unknown as BaseMessage,
      temp.directory,
      signal,
      downloader,
    );
    assert.equal(voice.text, "语音文本");
  } finally {
    temp.cleanup();
  }
});

test("超限文件和中途取消均清理本条消息的附件", async () => {
  const temp = temporary();
  const body = {
    ...fileMessage,
    quote: { msgtype: "image", image: { url: "https://example.com/image" } },
  } as unknown as BaseMessage;
  try {
    const controller = new AbortController();
    for (const abort of [false, true]) {
      const fetcher = async (url: RequestInfo | URL) => {
        if (String(url).endsWith("/image")) return new Response(png);
        if (!abort)
          return new Response("x", {
            headers: { "content-length": String(100 * 1024 * 1024 + 1) },
          });
        let first = true;
        return new Response(
          new ReadableStream({
            pull(stream) {
              if (first) {
                first = false;
                stream.enqueue(png);
              } else {
                controller.abort(new Error("cancelled"));
                stream.close();
              }
            },
          }),
        );
      };
      await assert.rejects(
        readWeComInput(body, temp.directory, controller.signal, fetcher),
        abort ? /cancelled/ : /100 MB/,
      );
      assert.deepEqual(readdirSync(temp.directory), []);
    }
  } finally {
    temp.cleanup();
  }
});

test("长连接附件使用每个 URL 的密钥解密，校验 32 字节填充", async () => {
  const temp = temporary();
  const key = randomBytes(32);
  const body = {
    msgtype: "image",
    image: { url: "https://example.com/image", aeskey: key.toString("base64") },
  } as unknown as BaseMessage;
  try {
    for (const valid of [true, false]) {
      const padding = Buffer.alloc(32 - png.length, 32 - png.length);
      if (!valid) padding[0] = 0;
      const cipher = createCipheriv(
        "aes-256-cbc",
        key,
        key.subarray(0, 16),
      ).setAutoPadding(false);
      const encrypted = Buffer.concat([
        cipher.update(png),
        cipher.update(padding),
        cipher.final(),
      ]);
      const result = readWeComInput(
        body,
        temp.directory,
        signal,
        async () =>
          new Response(
            new ReadableStream({
              start(s) {
                s.enqueue(encrypted.subarray(0, 7));
                s.enqueue(encrypted.subarray(7));
                s.close();
              },
            }),
          ),
      );
      if (valid)
        assert.deepEqual(
          readFileSync((await result).attachments[0]!.path),
          Buffer.from(png),
        );
      else await assert.rejects(result, /解密失败/);
    }
    assert.equal(readdirSync(temp.directory).length, 1);
  } finally {
    temp.cleanup();
  }
});
test("文本与 mixed 引用保留正文，移除当前提问的机器人前缀", async () => {
  const temp = temporary();
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
        {
          msgtype: "text",
          text: { content: "@机器人 帮我分析" },
          quote,
        } as unknown as BaseMessage,
        temp.directory,
        signal,
        noDownload,
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
  try {
    for (const quote of [
      { msgtype: "text", text: { content: "[该消息类型暂不能展示]" } },
      { msgtype: "unknown" },
      { msgtype: "text", text: {} },
      { msgtype: "markdown", markdown: { content: "未支持的内容块" } },
    ]) {
      const result = await readWeComInput(
        {
          msgtype: "text",
          text: { content: "@机器人 看 https://example.com/alert" },
          quote,
        } as unknown as BaseMessage,
        temp.directory,
        signal,
        noDownload,
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
