import { pipeline, Transform } from "node:stream";
import type { Readable } from "node:stream";
import { parser } from "stream-json/parser.js";
import { filter } from "stream-json/filters/filter.js";
import { streamValues } from "stream-json/streamers/stream-values.js";
import type { Token } from "stream-json/parser.js";
import { BridgeError } from "../types.js";

// 只组装协议需要的字段；工具参数与结果按块消费，不在桥接层累积。
const FIELDS =
  /^(?:|type|thread_id|session_id|subtype|is_error|timestamp_ms|model_call_id|text|result|item\.(?:type|id|text)|message\.content\.\d+\.(?:type|text))$/;

function guard(selected: boolean): Transform {
  let depth = 0;
  let size = 0;
  let keySize = 0;
  let inKey = false;
  let tokens = 0;
  let scalar = "";
  let scalarType: "string" | "number" | undefined;
  return new Transform({
    objectMode: true,
    transform(token: Token, _encoding, callback) {
      if (token.name === "startObject" || token.name === "startArray") {
        if (!depth) {
          size = 0;
          tokens = 0;
          if (token.name !== "startObject")
            return callback(new BridgeError("Agent 事件必须为 JSON 对象。"));
        }
        if (++depth > 256)
          return callback(new BridgeError("Agent 事件嵌套层级超出限制。"));
      }
      if (token.name === "startKey") {
        keySize = 0;
        inKey = true;
      }
      if (token.name === "stringChunk" || token.name === "numberChunk") {
        if (selected) size += token.value.length;
        else if (inKey) keySize += token.value.length;
      }
      // 原始流只限制键；工具结果的大字符串按块消费，不累计。
      if (!selected && keySize > 4096)
        return callback(new BridgeError("Agent 事件字段名超出限制。"));
      if (token.name === "endKey") inKey = false;
      if (selected && (size > 400_000 || ++tokens > 50_000))
        return callback(
          new BridgeError("Agent 回复超过长度上限，任务已终止。"),
        );
      if (token.name === "endObject" || token.name === "endArray") depth--;
      if (selected) {
        if (token.name === "startString" || token.name === "startNumber") {
          scalar = "";
          scalarType = token.name === "startString" ? "string" : "number";
          return callback();
        }
        if (token.name === "stringChunk" || token.name === "numberChunk") {
          if (scalarType) scalar += token.value;
          return callback();
        }
        if (token.name === "endString" || token.name === "endNumber") {
          const packed = {
            name: scalarType === "string" ? "stringValue" : "numberValue",
            value: scalar,
          };
          scalarType = undefined;
          scalar = "";
          return callback(null, packed);
        }
      }
      callback(null, token);
    },
  });
}

export async function* readAgentEvents(
  source: Readable,
  onActivity?: () => void,
): AsyncGenerator<string> {
  let finished!: () => void;
  const done = new Promise<void>((resolve) => {
    finished = resolve;
  });
  const stream = streamValues.asStream();
  pipeline(
    source,
    new Transform({
      transform(chunk, _encoding, callback) {
        onActivity?.();
        callback(null, chunk);
      },
    }),
    parser.asStream({
      jsonStreaming: true,
      packKeys: true,
      streamKeys: true,
      packStrings: false,
      packNumbers: false,
    }),
    guard(false),
    filter.asStream({ filter: FIELDS }),
    guard(true),
    stream,
    () => finished(),
  );
  try {
    for await (const event of stream) yield JSON.stringify(event.value);
  } catch (error) {
    if (error instanceof BridgeError) throw error;
    throw new BridgeError("Agent 输出了无效 JSON，任务已终止。");
  } finally {
    stream.destroy();
    await done;
  }
}
