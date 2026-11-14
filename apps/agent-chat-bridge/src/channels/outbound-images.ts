import { readFileSync, realpathSync, statSync } from "node:fs";
import { basename, relative, resolve, isAbsolute } from "node:path";
import { imageType } from "./wecom-input.js";

export function extractImages(
  text: string,
  workspace: string,
): { text: string; images: Array<{ filename: string; buffer: Buffer }> } {
  const images: Array<{ filename: string; buffer: Buffer }> = [];
  const seen = new Set<string>();
  const root = realpathSync(workspace);
  const result = text.replace(
    /!\[[^\]]*\]\(([^)\n]+)\)/g,
    (whole: string, path: string) => {
      if (/^(https?:|data:)/i.test(path)) return whole;
      try {
        const actual = realpathSync(resolve(root, path.replace(/^<|>$/g, "")));
        const inside = relative(root, actual);
        if (inside === ".." || inside.startsWith("../") || isAbsolute(inside))
          return "（图片不在允许的工作目录内。）";
        const stat = statSync(actual);
        if (!stat.isFile() || stat.size < 1 || stat.size > 10 * 1024 * 1024)
          return "（图片为空或超过大小限制。）";
        if (seen.has(actual)) return "";
        if (images.length >= 3) return "（每条回复最多发送 3 张图片。）";
        const buffer = readFileSync(actual);
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
