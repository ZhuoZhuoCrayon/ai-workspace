import {
  mkdirSync,
  mkdtempSync,
  realpathSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, sep } from "node:path";

// Cursor 按 --workspace 的词法路径向上查找规则。保留实际目录层级，以便项目及其祖先规则仍能被找到。
export function createCursorWorkspace(cwd: string, instructions: string) {
  const [top, ...rest] = realpathSync(cwd).split(sep).filter(Boolean);
  const root = mkdtempSync(
    join(realpathSync(tmpdir()), "bridge-cursor-rules-"),
  );
  const close = () => rmSync(root, { recursive: true, force: true });
  try {
    const rules = join(root, ".cursor", "rules");
    mkdirSync(rules, { recursive: true, mode: 0o700 });
    writeFileSync(
      join(rules, "bridge-channel.mdc"),
      "---\nalwaysApply: true\n---\n\n" + instructions + "\n",
      { mode: 0o600 },
    );
    const alias = join(root, "root");
    symlinkSync(join(sep, top ?? ""), alias, "dir");
    return { path: join(alias, ...rest), close };
  } catch (error) {
    close();
    throw error;
  }
}
