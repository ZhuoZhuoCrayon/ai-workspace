import test from "node:test";
import assert from "node:assert/strict";
import { splitMarkdownByBytes, stripBotMention } from "../src/channels/text.js";

const withinBudget = (parts: string[], budget: number): void => {
  assert(parts.length > 0);
  for (const part of parts) assert(Buffer.byteLength(part) <= budget);
};

const codeText = (parts: string[]): string =>
  parts
    .flatMap((part) => part.split("\n"))
    .filter((line) => !/^ {0,3}(?:`{3,}|~{3,})/.test(line))
    .join("");

test("纯文本分段保留字节和 Unicode 码点", () => {
  for (const text of ["a".repeat(19_950), "中😀ab".repeat(3000)]) {
    const parts = splitMarkdownByBytes(text, 4000);
    withinBudget(parts, 4000);
    assert.equal(parts.join(""), text);
    assert(parts.every((part) => !part.includes("�")));
  }
  assert.deepEqual(splitMarkdownByBytes("a\n\nb\n", 16), ["a\n\nb\n"]);
});

test("长代码行的重开围栏计入分段预算", () => {
  for (const language of ["typescript", "x".repeat(120)]) {
    const body = "a".repeat(9000);
    const parts = splitMarkdownByBytes(
      `\`\`\`${language}\n${body}\n\`\`\``,
      4000,
    );
    withinBudget(parts, 4000);
    assert.equal(codeText(parts), body);
    for (const part of parts) {
      assert.equal(
        part.split("\n").filter((line) => line.startsWith("```")).length,
        2,
      );
    }
  }
});

test("Unicode 代码、小预算和超长围栏标识都保持正文完整", () => {
  const body = "中😀".repeat(100);
  for (const budget of [16, 32, 64]) {
    const parts = splitMarkdownByBytes(
      `\`\`\`${"long-language".repeat(30)}\n${body}\n\`\`\``,
      budget,
    );
    withinBudget(parts, budget);
    assert.equal(codeText(parts), body);
  }
});

test("波浪围栏与未闭合代码块使用匹配的结束标记", () => {
  const body = "a".repeat(200);
  const parts = splitMarkdownByBytes(`~~~json\n${body}`, 64);
  withinBudget(parts, 64);
  assert.equal(codeText(parts), body);
  assert(
    parts.every((part) => part.startsWith("~~~json\n") && part.endsWith("~~~")),
  );
  const differentMarker = splitMarkdownByBytes(
    "````text\n```\n~~~\nbody\n````",
    64,
  );
  assert.deepEqual(differentMarker, ["````text\n```\n~~~\nbody\n````"]);
});

test("分段预算无效时拒绝，mention 处理保留换行和无分隔符原文", () => {
  for (const budget of [0, 15, 16.5, Number.NaN])
    assert.throws(() => splitMarkdownByBytes("text", budget), RangeError);
  assert.equal(
    stripBotMention("@Bot\u200b/agent cursor").text,
    "/agent cursor",
  );
  assert.equal(stripBotMention("@Bot没有分隔符").text, "@Bot没有分隔符");
  assert.equal(stripBotMention("@Bot hello\nworld").text, "hello\nworld");
});
