import { mkdtempSync, rmSync, writeFileSync, realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { IncomingMessage, Reply } from "../src/types.js";
import { randomUUID } from "node:crypto";

export const logger = { info() {}, error() {} };
export function temporary() {
  const directory = realpathSync(
    mkdtempSync(join(tmpdir(), "agent-chat-bridge-")),
  );
  return {
    directory,
    cleanup: () => rmSync(directory, { recursive: true, force: true }),
  };
}
export function message(
  text: string,
  overrides: Partial<IncomingMessage> = {},
): IncomingMessage {
  return {
    channel: "test",
    accountId: "bot",
    conversationId: "room",
    userId: "user",
    messageId: randomUUID(),
    text,
    ...overrides,
  };
}
export function reply(): Reply & { updates: string[]; finals: string[] } {
  return {
    updates: [],
    finals: [],
    async update(content) {
      this.updates.push(content);
    },
    async finish(content) {
      this.finals.push(content);
    },
  };
}
export function executable(directory: string, source: string): string {
  const file = join(directory, `${randomUUID()}.mjs`);
  writeFileSync(file, `#!${process.execPath}\n${source}`, { mode: 0o700 });
  return file;
}
