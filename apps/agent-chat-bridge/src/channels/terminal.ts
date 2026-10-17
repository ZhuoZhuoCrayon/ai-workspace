import { randomUUID } from "node:crypto";
import { createInterface } from "node:readline";
import type { Bridge } from "../bridge.js";
import type { Logger, Reply } from "../types.js";

export async function runTerminal(
  bridge: Bridge,
  logger: Logger,
): Promise<void> {
  if (process.stdin.isTTY)
    logger.info("终端已就绪：直接输入任务，/help 查看命令，Ctrl+D 退出。");
  const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
  for await (const text of input) {
    const reply: Reply = {
      async update(content) {
        if (process.stdout.isTTY) process.stdout.write(`[进度] ${content}\n`);
      },
      async finish(content) {
        process.stdout.write(`${content}\n`);
      },
    };
    void bridge
      .handle(
        {
          channel: "terminal",
          accountId: "local",
          conversationId: "terminal",
          userId: "local",
          messageId: randomUUID(),
          text,
        },
        reply,
      )
      .catch(() => logger.error("终端消息处理失败。"));
  }
  await bridge.idle();
}
