import { realpathSync, statSync } from "node:fs";
import { spawnSync } from "node:child_process";
import type { SpawnOptions } from "node:child_process";
import { fileURLToPath } from "node:url";
import { BridgeError } from "./types.js";

export interface ExecutionIdentity {
  uid: number;
  gid: number;
  home: string;
}

export function executionIdentity(raw: unknown): ExecutionIdentity | undefined {
  if (raw === undefined) return;
  const value = raw as ExecutionIdentity;
  if (
    !value ||
    !Number.isSafeInteger(value.uid) ||
    value.uid <= 0 ||
    !Number.isSafeInteger(value.gid) ||
    value.gid <= 0 ||
    typeof value.home !== "string"
  )
    throw new BridgeError(
      "execution 必须配置非 root 的 uid、gid 和独立 home。",
    );
  const home = realpathSync(value.home);
  const info = statSync(home);
  if (!info.isDirectory() || info.uid !== value.uid || info.mode & 0o077)
    throw new BridgeError("execution.home 必须由执行账号拥有且权限为 0700。");
  return { uid: value.uid, gid: value.gid, home };
}

export function agentEnvironment(
  identity?: ExecutionIdentity,
): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {};
  // 独立账号只继承运行工具必需的非凭据环境；登录与工具配置由独立 HOME 管理。
  const allowed = new Set(["PATH", "LANG", "LC_ALL", "TZ", "TERM"]);
  for (const [key, value] of Object.entries(process.env)) {
    if (
      identity
        ? allowed.has(key)
        : !key.startsWith("WECOM_") && !key.startsWith("BRIDGE_")
    )
      env[key] = value;
  }
  if (identity) {
    env.HOME = identity.home;
    env.XDG_CONFIG_HOME = `${identity.home}/.config`;
  }
  return env;
}

export function executionOptions(
  identity?: ExecutionIdentity,
): Pick<SpawnOptions, "uid" | "gid" | "env"> {
  return {
    env: agentEnvironment(identity),
    ...(identity ? { uid: identity.uid, gid: identity.gid } : {}),
  };
}

/** 用真实降权子进程验证权限。配置、凭据及会话状态均须对执行账号不可读写。 */
export function assertExecutionBoundary(
  identity: ExecutionIdentity,
  protectedPaths: string[],
  nodeCommand = process.execPath,
): void {
  if (process.getuid?.() !== 0 || identity.uid === process.getuid())
    throw new BridgeError(
      "独立执行账号需要 root 控制进程启动，且 uid 必须不同。",
    );
  const probe = spawnSync(
    nodeCommand,
    [
      "--input-type=module",
      "-e",
      `
    import fs from 'node:fs';
    import path from 'node:path';
    if (process.getuid() === 0 || process.getgroups().includes(0)) process.exit(2);
    const [privatePaths, readOnlyPaths] = JSON.parse(process.argv[1]);
    for (const [names, denyRead] of [[privatePaths, true], [readOnlyPaths, false]]) for (const name of names) {
      if (denyRead) { try { fs.accessSync(name, fs.constants.R_OK); process.exit(3); } catch {} }
      try { fs.accessSync(name, fs.constants.W_OK); process.exit(3); } catch {}
      let entry = name;
      while (entry !== path.dirname(entry)) {
        const parent = path.dirname(entry);
        let writable = false;
        try { fs.accessSync(parent, fs.constants.W_OK); writable = true; } catch {}
        if (writable) {
          try {
            const directory = fs.statSync(parent), child = fs.lstatSync(entry);
            // sticky 目录中，非目录所有者无法替换他人已有的条目。
            if (!(directory.mode & 0o1000) || directory.uid === process.getuid() || child.uid === process.getuid()) process.exit(4);
          } catch { process.exit(4); }
        }
        entry = parent;
      }
    }
  `,
      JSON.stringify([
        protectedPaths,
        [process.execPath, fileURLToPath(new URL(".", import.meta.url))],
      ]),
    ],
    { ...executionOptions(identity), encoding: "utf8", timeout: 5000 },
  );
  if (probe.status !== 0)
    throw new BridgeError("执行账号可访问管理配置或权限探测失败，拒绝启动。");
}
