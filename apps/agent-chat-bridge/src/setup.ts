import {
  existsSync,
  linkSync,
  readFileSync,
  renameSync,
  writeFileSync,
  unlinkSync,
  realpathSync,
  statSync,
} from "node:fs";
import { resolve, join, dirname } from "node:path";
import { randomUUID } from "node:crypto";
import { createInterface } from "node:readline/promises";
import { Writable } from "node:stream";
import { parseEnv } from "node:util";
import { BridgeError } from "./types.js";
import { validUserId } from "./access.js";
import { DEFAULT_TASK_TIMEOUTS } from "./config.js";

export interface SetupPrompt {
  ask(label: string, secret?: boolean): Promise<string>;
  close(): void;
}

export function terminalPrompt(): SetupPrompt {
  let hidden = false;
  const output = new Writable({
    write(chunk, _encoding, callback) {
      if (!hidden) process.stdout.write(chunk);
      callback();
    },
  });
  const input = createInterface({
    input: process.stdin,
    output,
    terminal: Boolean(process.stdin.isTTY && process.stdout.isTTY),
  });
  return {
    async ask(label, secret = false) {
      process.stdout.write(label);
      hidden = secret;
      try {
        return (await input.question("")).trim();
      } finally {
        hidden = false;
        if (secret) process.stdout.write("\n");
      }
    },
    close() {
      input.close();
    },
  };
}

export async function initialize(
  directory: string,
  prompt: SetupPrompt = terminalPrompt(),
): Promise<string> {
  const file = join(directory, "bridge.local.json");
  try {
    if (existsSync(file)) return file;
    const channel =
      (await prompt.ask("聊天平台 wecom / terminal [wecom]：")) || "wecom";
    if (!["wecom", "terminal"].includes(channel))
      throw new BridgeError("平台只能选择 wecom 或 terminal。");
    const workspace = realpathSync(
      resolve(
        directory,
        (await prompt.ask("Agent 工作目录 [当前目录]：")) || ".",
      ),
    );
    if (!statSync(workspace).isDirectory())
      throw new BridgeError("Agent 工作目录必须是已存在的目录。");
    const agent =
      (await prompt.ask("默认执行器 codex / cursor [codex]：")) || "codex";
    if (!["codex", "cursor"].includes(agent))
      throw new BridgeError("执行器只能选择 codex 或 cursor。");
    const writable = /^(y|yes|是)$/i.test(
      await prompt.ask("允许 Agent 修改工作目录？y / N："),
    );
    const envFile = join(directory, ".env");
    let credentials: string | undefined;
    if (channel === "wecom") {
      const existing = existsSync(envFile)
        ? parseEnv(readFileSync(envFile, "utf8"))
        : undefined;
      if (existing) {
        if (!existing.WECOM_BOT_ID || !existing.WECOM_BOT_SECRET)
          throw new BridgeError(
            "已有 .env 缺少机器人凭据，请补齐 WECOM_BOT_ID 和 WECOM_BOT_SECRET 后重试，向导不会覆盖原文件。",
          );
      } else {
        const botId = await prompt.ask("企业微信 Bot ID：");
        const secret = await prompt.ask(
          "企业微信 Bot Secret（隐藏输入）：",
          true,
        );
        if (!botId || !secret || /[\r\n]/.test(botId + secret))
          throw new BridgeError("机器人凭据不能为空或包含换行。");
        const encode = (key: string, value: string): string => {
          for (const quote of ["'", "`", '"']) {
            const line = `${key}=${quote}${value}${quote}`;
            if (parseEnv(line)[key] === value) return line;
          }
          throw new BridgeError(
            "凭据引号格式无法安全保存，请改用环境变量提供凭据。",
          );
        };
        credentials = `${encode("WECOM_BOT_ID", botId)}\n${encode("WECOM_BOT_SECRET", secret)}\n`;
      }
    }
    if (credentials)
      writeFileSync(envFile, credentials, { flag: "wx", mode: 0o600 });
    const config = {
      channel,
      workspace,
      defaultAgent: agent,
      ...DEFAULT_TASK_TIMEOUTS,
      agents: { codex: { writable }, cursor: { writable } },
      wecom: { allowedUsers: [] },
    };
    const temporary = join(directory, `.setup-${randomUUID()}.tmp`);
    try {
      writeFileSync(temporary, JSON.stringify(config, null, 2) + "\n", {
        flag: "wx",
        mode: 0o600,
      });
      // 完整写入后才公开配置，目标已存在时原子拒绝覆盖。
      linkSync(temporary, file);
    } catch {
      if (credentials && readFileSync(envFile, "utf8") === credentials)
        unlinkSync(envFile);
      throw new BridgeError("配置写入失败，请检查目录权限后重新运行向导。");
    } finally {
      if (existsSync(temporary)) unlinkSync(temporary);
    }
    return file;
  } finally {
    prompt.close();
  }
}

export function savePairedUser(file: string, userId: string): void {
  if (!validUserId(userId)) throw new BridgeError("用户 ID 无效。");
  const config = JSON.parse(readFileSync(file, "utf8"));
  const previous = config.wecom?.allowedUsers ?? [];
  if (!Array.isArray(previous)) throw new BridgeError("白名单格式无效。");
  const next = {
    ...config,
    wecom: {
      ...config.wecom,
      allowedUsers: [...new Set([...previous, userId])],
      adminUsers: previous.length ? (config.wecom?.adminUsers ?? []) : [userId],
    },
  };
  const temporary = join(dirname(file), `.pair-${randomUUID()}.tmp`);
  try {
    writeFileSync(temporary, JSON.stringify(next, null, 2) + "\n", {
      mode: 0o600,
      flag: "wx",
    });
    renameSync(temporary, file);
  } finally {
    if (existsSync(temporary)) unlinkSync(temporary);
  }
}
