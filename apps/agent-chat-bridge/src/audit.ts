import {
  appendFileSync,
  mkdirSync,
  lstatSync,
  openSync,
  closeSync,
  fstatSync,
  constants,
  existsSync,
  renameSync,
  unlinkSync,
} from "node:fs";
import { dirname } from "node:path";
import { createHash } from "node:crypto";
import type { IncomingMessage } from "./types.js";

export interface AuditEvent {
  action: string;
  message?: IncomingMessage;
  target?: string;
  result?: string;
  agent?: string;
}
export interface AuditSink {
  record(event: AuditEvent): void;
}

/** 固定字段日志，不接受正文、工具输出、环境变量或异常消息。写入失败由调用方拒绝操作。 */
export class AuditLog implements AuditSink {
  constructor(
    private readonly file: string,
    private readonly maxBytes = 10 * 1024 * 1024,
    private readonly workspace?: string,
  ) {
    if (!Number.isSafeInteger(maxBytes) || maxBytes < 1)
      throw new Error("审计文件大小上限无效。");
    mkdirSync(dirname(file), { recursive: true, mode: 0o700 });
    const directory = lstatSync(dirname(file));
    if (!directory.isDirectory() || directory.mode & 0o077)
      throw new Error("审计目录必须私有。");
  }
  record(event: AuditEvent): void {
    const fingerprint = (value: string): string =>
      createHash("sha256").update(value).digest("hex").slice(0, 24);
    const entry = {
      time: new Date().toISOString(),
      action: event.action,
      ...(this.workspace ? { workspace: fingerprint(this.workspace) } : {}),
      ...(event.message
        ? {
            userId: event.message.userId,
            message: fingerprint(event.message.messageId),
            conversation: fingerprint(event.message.conversationId),
          }
        : {}),
      ...(event.target ? { target: event.target } : {}),
      ...(event.result ? { result: event.result } : {}),
      ...(event.agent ? { agent: event.agent } : {}),
    };
    let fd = openSync(
      this.file,
      constants.O_WRONLY |
        constants.O_APPEND |
        constants.O_CREAT |
        constants.O_NOFOLLOW,
      0o600,
    );
    try {
      const info = fstatSync(fd);
      if (
        !info.isFile() ||
        info.mode & 0o077 ||
        info.uid !== process.getuid?.()
      )
        throw new Error("审计文件权限无效。");
      if (info.size >= this.maxBytes) {
        closeSync(fd);
        fd = -1;
        if (existsSync(`${this.file}.3`)) unlinkSync(`${this.file}.3`);
        for (let index = 2; index >= 0; index--) {
          const source = index ? `${this.file}.${index}` : this.file;
          if (existsSync(source))
            renameSync(source, `${this.file}.${index + 1}`);
        }
        fd = openSync(
          this.file,
          constants.O_WRONLY |
            constants.O_APPEND |
            constants.O_CREAT |
            constants.O_NOFOLLOW,
          0o600,
        );
      }
      appendFileSync(fd, JSON.stringify(entry) + "\n");
    } finally {
      if (fd !== -1) closeSync(fd);
    }
  }
}
