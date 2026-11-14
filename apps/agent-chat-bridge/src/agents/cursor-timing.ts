import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

// 一次 CLI 调用有独立的临时 workspace，即使 resume 也不会复用。
export function cursorTiming(workspace: string, env: NodeJS.ProcessEnv) {
  const data =
    env.BK_APM_CURSOR_DATA_DIR ||
    join(homedir(), ".cursor", "bk-apm-cursor-tracing");
  try {
    if (
      JSON.parse(readFileSync(join(data, "config.json"), "utf8")).enabled !==
      true
    )
      return;
  } catch {
    return;
  }
  const project = workspace.match(
    /\/(bridge-cursor-rules-[A-Za-z0-9]{6})\/root(?:\/|$)/,
  )?.[1];
  if (!project) return;
  const dir = join(data, "cli-timing");
  const epoch = Date.now();
  const base = performance.now();
  let session: string | undefined;
  let started: number | undefined;
  let assistant: number | undefined;
  let invalid = false;
  const tools: { id: string; start: number; end?: number }[] = [];
  return (value: Record<string, unknown>) => {
    if (invalid) return;
    const at = epoch + Math.round(performance.now() - base);
    if (typeof value.session_id === "string") {
      if (session && session !== value.session_id) {
        invalid = true;
        return;
      }
      session = value.session_id;
    }
    if (value.type === "user") {
      if (started !== undefined) invalid = true;
      started = at;
    } else if (value.type === "tool_call") {
      const id = value.call_id;
      if (
        typeof id !== "string" ||
        !id ||
        id.length > 512 ||
        started === undefined
      ) {
        invalid = true;
        return;
      }
      if (value.subtype === "started") {
        if (tools.length >= 256 || tools.some((t) => t.id === id)) {
          invalid = true;
          return;
        }
        tools.push({ id, start: at });
        assistant = undefined;
      } else if (value.subtype === "completed") {
        const tool = tools.find((t) => t.id === id);
        if (!tool || tool.end !== undefined) {
          invalid = true;
          return;
        }
        tool.end = at;
      }
    } else if (value.type === "assistant") {
      assistant = at;
    } else if (value.type === "result") {
      invalid = true;
      if (
        value.subtype !== "success" ||
        value.is_error ||
        !session ||
        started === undefined ||
        assistant === undefined ||
        tools.some((t) => t.end === undefined || t.end > assistant!)
      )
        return;
      const key = createHash("sha256")
        .update(JSON.stringify([project, session]))
        .digest("hex");
      try {
        mkdirSync(dir, { recursive: true, mode: 0o700 });
        const target = join(dir, key + ".json");
        const temp = target + "." + process.pid + ".tmp";
        writeFileSync(
          temp,
          JSON.stringify({
            version: 1,
            session,
            start: started,
            end: assistant,
            tools,
          }),
          { mode: 0o600 },
        );
        renameSync(temp, target);
      } catch {
        /* 可选的本机采集器不可用，不影响用户回复。 */
      }
    }
  };
}
