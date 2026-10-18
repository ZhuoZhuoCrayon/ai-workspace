function webTarget(target: string): boolean {
  return /^https?:\/\//i.test(target) || /^mailto:/i.test(target);
}

function plainReference(label: string, target: string): string {
  const path = target.replace(/`/g, "");
  return label.replace(/`/g, "") === path
    ? `\`${path}\``
    : `${label}（\`${path}\`）`;
}

/** 聊天客户端无法打开开发机链接；保留路径文字，不猜远程版本。 */
export function portableLinks(markdown: string): string {
  const references = new Map<string, string>();
  const normalize = (id: string): string =>
    id.trim().replace(/\s+/g, " ").toLowerCase();
  const token =
    /(^ {0,3}(`{3,}|~{3,})[^\n]*\n[\s\S]*?^ {0,3}\2[ \t]*(?=\n|$))|(`+)[^\n]*?\3|^ {0,3}\[([^\]\n]+)\]:[ \t]*(?:<([^>\n]+)>|(\S+))[^\n]*$/gm;
  const withoutDefinitions = markdown.replace(
    token,
    (match, fence, _marker, inline, id, angle, bare) => {
      if (fence || inline) return match;
      const target = angle ?? bare;
      if (webTarget(target)) return match;
      references.set(normalize(id), target);
      return "";
    },
  );
  const links =
    /(^ {0,3}(`{3,}|~{3,})[^\n]*\n[\s\S]*?^ {0,3}\2[ \t]*(?=\n|$))|(`+)[^\n]*?\3|(!?)\[([^\]\n]+)\]\([ \t]*(?:<([^>\n]+)>|((?:[^\s()]|\([^()\n]*\))+))(?:[ \t]+["'][^\n]*?["'])?[ \t]*\)|(!?)\[([^\]\n]+)\](?:\[([^\]\n]*)\])?|<((?:file|vscode|cursor|codex):[^>\n]+)>/gm;
  return withoutDefinitions.replace(
    links,
    (
      match,
      fence,
      _marker,
      inline,
      image,
      label,
      angle,
      bare,
      refImage,
      refLabel,
      id,
      auto,
    ) => {
      if (fence || inline || image || refImage) return match;
      if (auto) return plainReference(auto, auto);
      if (label !== undefined) {
        const target = angle ?? bare;
        return webTarget(target) ? match : plainReference(label, target);
      }
      const target = references.get(normalize(id || refLabel));
      return target ? plainReference(refLabel, target) : match;
    },
  );
}
