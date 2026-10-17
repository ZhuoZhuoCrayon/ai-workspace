/** 企业微信消息按 UTF-8 字节处理，避免拆坏中文或 emoji。 */
function byteLength(text: string): number {
  return Buffer.byteLength(text);
}

function clampToBytes(text: string, maxBytes: number): string {
  if (byteLength(text) <= maxBytes) return text;
  let result = "";
  let size = 0;
  for (const character of text) {
    const bytes = byteLength(character);
    if (size + bytes > maxBytes) break;
    result += character;
    size += bytes;
  }
  return result;
}

/**
 * 分隔 @名字 与正文的「广义空白」。
 *
 * JS 的 `\s` 已含 NBSP、全角空格与 U+2000–U+200A，但**不含零宽系列 U+200B–U+200F**。
 * 企微客户端在 @ 之后插入的未必是普通空格，一旦是零宽字符，`\S+` 就会把它连同后面的
 * 正文一起吃掉。这类字符 `JSON.stringify` 也不转义，日志里与「根本没有分隔符」长得一样，
 * 极难看出来——所以这里按码点显式列出，而不是依赖 `\s`。
 */
const BLANK = "\\s\\u200b-\\u200f";
/** 群聊消息开头的 @机器人 前缀；要求其后至少有一个分隔符，否则无从判断名字在哪结束。 */
const MENTION_PREFIX = new RegExp(`^(?:[${BLANK}]*@[^${BLANK}]+[${BLANK}]+)+`);
/** 开头单个 @token 的形状，用于在「整条只有一个 @」时取出名字。 */
const LEADING_MENTION = new RegExp(`^[${BLANK}]*(@[^${BLANK}]+)[${BLANK}]+`);

export interface MentionStrip {
  /** 摘掉 @机器人 后的正文。名字边界无从判断时退回原文，绝不返回空串。 */
  text: string;
  /** 本次认出的 @机器人 token（含 @、不含分隔符），无法确证是本机器人时不给。 */
  mention?: string | undefined;
}

/**
 * 摘掉群聊消息里的 @机器人。
 *
 * 企微不提供结构化的 mention（官方回调示例就是 `"content": "@RobotA hello robot"`，
 * 字段表里也没有 mention 结构），只能按字符串处理，而字符串这边有两个坑：
 *
 * 一是**分隔符并不总是存在**：真机实测，用户手打时企微会插一个空格，但点击 `jump_list`
 * 代发的消息里 @名字 与正文是直接拼接的。旧规则 `^(\s*@\S+\s*)+` 的 `\S+` 遇到后者会
 * 把整条吃光，用户那句话被当成「没收到有效的问题内容」丢掉。
 *
 * 二是 **@ 的位置是自由的**：`@张三 帮我看看 @机器人` 完全合法，开头那个 @ 未必是自己。
 *
 * 所以名字只在能确证时才学：企微只投递「@ 了机器人」的群消息，故**整条消息里只出现一个
 * @ 时，它必然是本机器人**；出现多个就无从分辨，宁可不学。一旦学到名字（`known`），@ 在
 * 句首句中句末都能精确摘掉；没学到就只按分隔符剥开头，再不行退回原文——宁可让 agent 多
 * 看见一个 @前缀，也不能把人说的话整条弄丢。
 */
export function stripBotMention(raw: string, known?: string): MentionStrip {
  if (known && raw.includes(known)) {
    // 换成空格而不是直接删：`看看@机器人这个问题` 删掉后会把两边的词粘成一个
    const text = collapseSpaces(raw.split(known).join(" "));
    if (text) return { text };
  }
  const matched = MENTION_PREFIX.exec(raw);
  if (matched) {
    const text = raw.slice(matched[0].length).trim();
    if (text) {
      const lone = countChar(raw, "@") === 1 ? LEADING_MENTION.exec(raw) : null;
      return { text, mention: lone ? lone[1] : undefined };
    }
  }
  return { text: raw.trim() };
}

function countChar(s: string, ch: string): number {
  let n = 0;
  for (const c of s) if (c === ch) n += 1;
  return n;
}

/** 只压水平空白，换行与段落结构保持原样。 */
function collapseSpaces(s: string): string {
  return s
    .replace(/[^\S\r\n]{2,}/g, " ")
    .replace(/[^\S\r\n]+$/gm, "")
    .trim();
}

interface Fence {
  marker: string;
  info: string;
}

function openingFence(line: string): Fence | undefined {
  const match = /^ {0,3}(`{3,}|~{3,})(.*)$/.exec(line);
  if (!match || (match[1]!.startsWith("`") && match[2]!.includes("`"))) return;
  return { marker: match[1]!, info: match[2]! };
}

function closesFence(line: string, fence: Fence): boolean {
  const match = /^ {0,3}(`{3,}|~{3,})[ \t]*$/.exec(line);
  return Boolean(
    match &&
    match[1]![0] === fence.marker[0] &&
    match[1]!.length >= fence.marker.length,
  );
}

/**
 * 每段独立闭合围栏，重开围栏和 Unicode 码点都计入字节预算。
 * 超出单段容量的围栏标识降级为无语言的三字符围栏，代码正文保持完整。
 */
export function splitMarkdownByBytes(text: string, maxBytes: number): string[] {
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 16)
    throw new RangeError("Markdown 分段预算至少为 16 字节。");
  if (!text) return [""];
  const chunks: string[] = [];
  let current = "";
  let hasContent = false;
  let fence: Fence | undefined;

  const flush = (): void => {
    if (!hasContent) return;
    const closing = fence
      ? `${current.endsWith("\n") ? "" : "\n"}${fence.marker}`
      : "";
    chunks.push(current + closing);
    current = fence ? `${fence.marker}${fence.info}\n` : "";
    hasContent = false;
  };

  const append = (source: string): void => {
    let rest = source;
    while (rest) {
      const reserved = fence ? byteLength(`\n${fence.marker}`) : 0;
      const available = maxBytes - byteLength(current) - reserved;
      const part = clampToBytes(rest, available);
      if (!part) {
        flush();
        continue;
      }
      current += part;
      hasContent = true;
      rest = rest.slice(part.length);
      if (rest) flush();
    }
  };

  const lines = text.split("\n");
  for (let index = 0; index < lines.length; index++) {
    const line = lines[index]!;
    const newline = index < lines.length - 1 ? "\n" : "";
    if (fence && closesFence(line, fence)) {
      const marker = fence.marker;
      fence = undefined;
      append(marker + newline);
      continue;
    }
    const next = fence ? undefined : openingFence(line);
    if (next) {
      let header = line;
      if (
        byteLength(`${next.marker}${next.info}\n\n${next.marker}`) >
        maxBytes - 4
      ) {
        next.info = "";
        if (byteLength(`${next.marker}\n\n${next.marker}`) > maxBytes - 4)
          next.marker = next.marker.slice(0, 3);
        header = next.marker;
      }
      if (
        byteLength(current + header + newline + `\n${next.marker}`) > maxBytes
      )
        flush();
      fence = next;
      append(header + newline);
    } else {
      append(line + newline);
    }
  }
  flush();
  return chunks;
}
