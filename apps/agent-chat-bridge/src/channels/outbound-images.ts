import {
  readSync,
  realpathSync,
  fstatSync,
  openSync,
  closeSync,
  constants,
} from "node:fs";
import { basename, relative, resolve, isAbsolute } from "node:path";
import { imageType } from "./wecom-input.js";

export function extractImages(
  text: string,
  workspace: string,
): { text: string; images: Array<{ filename: string; buffer: Buffer }> } {
  const images: Array<{ filename: string; buffer: Buffer }> = [];
  const seen = new Set<string>();
  const root = workspace;
  if (realpathSync(root) !== root)
    return { text: "图片工作目录已变更，请联系管理员。", images: [] };
  const result = text.replace(
    /!\[[^\]]*\]\(([^)\n]+)\)/g,
    (whole: string, path: string) => {
      if (/^(https?:|data:)/i.test(path)) return whole;
      try {
        const actual = realpathSync(resolve(root, path.replace(/^<|>$/g, "")));
        const inside = relative(root, actual);
        if (inside === ".." || inside.startsWith("../") || isAbsolute(inside))
          return "（图片不在允许的工作目录内。）";
        const fd = openSync(actual, constants.O_RDONLY | constants.O_NOFOLLOW);
        let buffer: Buffer;
        try {
          // 控制进程权限高于 Agent，必须检查已打开的文件，而不是可被并发替换的路径。
          const opened = realpathSync(
            `${process.platform === "linux" ? "/proc/self/fd" : "/dev/fd"}/${fd}`,
          );
          const location = relative(root, opened);
          if (
            location === ".." ||
            location.startsWith("../") ||
            isAbsolute(location)
          )
            return "（图片不在允许的工作目录内。）";
          const stat = fstatSync(fd);
          if (!stat.isFile() || stat.size < 1 || stat.size > 10 * 1024 * 1024)
            return "（图片为空或超过大小限制。）";
          if (seen.has(actual)) return "";
          if (images.length >= 3) return "（每条回复最多发送 3 张图片。）";
          buffer = Buffer.alloc(stat.size);
          let read = 0;
          while (read < buffer.length) {
            const count = readSync(
              fd,
              buffer,
              read,
              buffer.length - read,
              read,
            );
            if (!count) break;
            read += count;
          }
          buffer = buffer.subarray(0, read);
        } finally {
          closeSync(fd);
        }
        const type = imageType(buffer);
        if (!type || !["image/png", "image/jpeg"].includes(type.mimeType))
          return "（出站图片仅支持 PNG 或 JPEG。）";
        seen.add(actual);
        images.push({ filename: basename(actual), buffer });
        return "";
      } catch {
        return "（图片读取失败。）";
      }
    },
  );
  return { text: result.trim(), images };
}
