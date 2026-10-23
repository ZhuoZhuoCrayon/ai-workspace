import {
  readFileSync,
  writeFileSync,
  renameSync,
  unlinkSync,
  existsSync,
  lstatSync,
} from "node:fs";
import { randomUUID } from "node:crypto";
import { dirname, join } from "node:path";
import { BridgeError } from "./types.js";
import type { IncomingMessage } from "./types.js";
import type { AuditSink } from "./audit.js";

export function validUserId(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}$/.test(value)
  );
}

export function userIds(value: unknown): string[] {
  if (
    !Array.isArray(value) ||
    !value.every(validUserId) ||
    new Set(value).size !== value.length
  )
    throw new BridgeError("用户列表必须是不重复的明确用户 ID。");
  return [...value];
}

/** 授权只读取受保护的配置；失效、损坏或缺失时拒绝请求。 */
export class AccessControl {
  constructor(
    private readonly file: string,
    private readonly audit: AuditSink,
    private readonly onRevoke?: (userId: string) => void,
  ) {}

  private read(): {
    raw: Record<string, unknown> & { wecom: Record<string, unknown> };
    users: string[];
    admins: string[];
  } {
    const info = lstatSync(this.file);
    if (!info.isFile() || info.mode & 0o077 || info.uid !== process.getuid?.())
      throw new BridgeError("授权配置必须是普通文件。");
    const raw = JSON.parse(readFileSync(this.file, "utf8"));
    if (
      !raw ||
      typeof raw !== "object" ||
      !raw.wecom ||
      typeof raw.wecom !== "object" ||
      Array.isArray(raw.wecom)
    )
      throw new BridgeError("授权配置格式无效。");
    const users = userIds(raw.wecom?.allowedUsers ?? []);
    const admins = userIds(raw.wecom?.adminUsers ?? []);
    if (!admins.every((id) => users.includes(id)))
      throw new BridgeError("管理员必须在白名单内。");
    return { raw, users, admins };
  }

  ready(): boolean {
    try {
      const { users, admins } = this.read();
      return users.length > 0 && admins.length > 0;
    } catch {
      return false;
    }
  }

  allowed(message: IncomingMessage): boolean {
    try {
      return this.read().users.includes(message.userId);
    } catch {
      return false;
    }
  }

  admin(message: IncomingMessage): boolean {
    try {
      return this.read().admins.includes(message.userId);
    } catch {
      return false;
    }
  }

  /** 仅处理平台直接传来的原始指令，不从引用、附件或模型输出解释管理操作。 */
  command(message: IncomingMessage): string | undefined {
    const input = message.text.trim();
    if (!/^\/(?:whoami|access|allow|deny)(?:\s|$)/.test(input)) return;
    const [name, target, ...rest] = input.split(/\s+/);
    if (name === "/whoami" && !target)
      return `你的 userid：${message.userId}\n角色：${this.admin(message) ? "管理员" : this.allowed(message) ? "使用者" : "未授权"}`;
    if (!this.admin(message)) {
      this.audit.record({
        action: "access.denied",
        message,
        result: "not_admin",
      });
      return "此操作仅限管理员。请将自己的 userid 提供给管理员，由其发送 /allow <userid>。";
    }
    const { raw, users, admins } = this.read();
    if (!admins.includes(message.userId))
      throw new BridgeError("管理员权限已撤销。");
    if (name === "/access" && !target)
      return `管理员：${admins.join("、") || "未配置"}\n使用者：${users.join("、") || "无"}`;
    if (
      !["/allow", "/deny"].includes(name!) ||
      !validUserId(target) ||
      rest.length
    )
      return "用法：/whoami、/access、/allow <userid>、/deny <userid>。管理员名单只能在本机配置。";
    if (name === "/deny" && admins.includes(target))
      return "不能通过聊天撤销管理员。请在本机调整管理员及白名单。";
    const next =
      name === "/allow"
        ? [...new Set([...users, target])]
        : users.filter((id) => id !== target);
    if (JSON.stringify(next) === JSON.stringify(users))
      return `${target} ${name === "/allow" ? "已在白名单内" : "不在白名单内"}。`;
    this.audit.record({
      action: "access.change_requested",
      message,
      target,
      result: name === "/allow" ? "allow" : "deny",
    });
    const temporary = join(dirname(this.file), `.access-${randomUUID()}.tmp`);
    try {
      raw.wecom = { ...raw.wecom, allowedUsers: next };
      writeFileSync(temporary, JSON.stringify(raw, null, 2) + "\n", {
        flag: "wx",
        mode: 0o600,
      });
      renameSync(temporary, this.file);
    } finally {
      if (existsSync(temporary)) unlinkSync(temporary);
    }
    if (name === "/deny") this.onRevoke?.(target);
    this.audit.record({
      action: "access.changed",
      message,
      target,
      result: name === "/allow" ? "allowed" : "revoked",
    });
    return `${target} ${name === "/allow" ? "已加入白名单" : "已撤销访问权限"}，立即生效。`;
  }
}
