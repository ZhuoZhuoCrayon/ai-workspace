import type { Progress } from "../types.js";

export function renderProgress(
  content: string,
  progress?: Progress,
  finished = false,
): string {
  if (!progress?.content) return content;
  const safe = progress.content
    .replace(/<\/?think\b[^>]*>/gi, (tag) =>
      tag.replace(/</g, "＜").replace(/>/g, "＞"),
    )
    .replace(/```|~~~/g, "");
  let summary = "";
  let bytes = 0;
  for (const character of [...safe].reverse()) {
    const size = Buffer.byteLength(character);
    if (bytes + size > 1500) break;
    summary = character + summary;
    bytes += size;
  }
  const closed = finished || !progress.active || Boolean(content);
  return `<think>${summary}${closed ? "</think>" : ""}${content ? `\n\n${content}` : ""}`;
}
