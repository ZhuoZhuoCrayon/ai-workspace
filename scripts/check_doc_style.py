#!/usr/bin/env python3
"""Check Markdown and MDC files against workspace doc-style rules."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT: Path = Path(__file__).resolve().parents[1]
DOC_SUFFIXES: set[str] = {".md", ".mdc"}
EXCLUDED_PARTS: set[str] = {".git", "node_modules", "__pycache__", ".venv", "venv"}
EXCLUDED_PREFIXES: tuple[str, ...] = (".agents/skills/", ".claude/skills/", ".codex/skills/", ".cursor/skills/")
SPECIAL_FILENAMES: set[str] = {
    "README.md",
    "PLAN.md",
    "PROGRESS.md",
    "INDEX.md",
    "AGENTS.md",
    "CLAUDE.md",
    "CODEX.md",
    "SKILL.md",
}
NUMBERED_SECTION_BASENAMES: set[str] = {"README.md", "PLAN.md", "PROGRESS.md", "SKILL.md"}
STRUCTURE_EXEMPT_BASENAMES: set[str] = {"INDEX.md", "AGENTS.md", "CLAUDE.md", "CODEX.md"}
FILENAME_PATTERN: re.Pattern[str] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\.(md|mdc)$")
FENCE_PATTERN: re.Pattern[str] = re.compile(r"^```([A-Za-z0-9_+#.-]+)?\s*$")
HEADING_PATTERN: re.Pattern[str] = re.compile(r"^(#{1,6})\s+(.*)$")
INLINE_CODE_PATTERN: re.Pattern[str] = re.compile(r"`[^`]*`")
URL_PATTERN: re.Pattern[str] = re.compile(r"https?://\S+")
ELLIPSIS_PATTERN: re.Pattern[str] = re.compile(r"(?<!\.)\.\.\.(?!\.)")
CJK_LATIN_PATTERN: re.Pattern[str] = re.compile(r"[\u4e00-\u9fff][A-Za-z]|[A-Za-z][\u4e00-\u9fff]")


@dataclass(frozen=True)
class Issue:
    path: str
    line: int
    rule: str
    message: str


def is_excluded(path: Path) -> bool:
    rel_path: str = path.relative_to(ROOT).as_posix()
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return True
    return any(rel_path.startswith(prefix) for prefix in EXCLUDED_PREFIXES)


def iter_target_files(explicit_files: list[str], scan_all: bool) -> list[Path]:
    candidates: list[Path] = []

    if explicit_files:
        raw_path: str
        for raw_path in explicit_files:
            candidate: Path = Path(raw_path)
            if not candidate.is_absolute():
                candidate = ROOT / candidate
            if candidate.exists() and candidate.is_file():
                candidates.append(candidate.resolve())
    elif scan_all:
        candidate = None
        for candidate in ROOT.rglob("*"):
            if candidate.is_file():
                candidates.append(candidate.resolve())
    else:
        raise ValueError("Must provide files or use --all")

    unique: list[Path] = []
    seen: set[Path] = set()
    candidate_path: Path
    for candidate_path in sorted(candidates):
        if candidate_path in seen:
            continue
        seen.add(candidate_path)
        if candidate_path.suffix not in DOC_SUFFIXES:
            continue
        if is_excluded(candidate_path):
            continue
        unique.append(candidate_path)

    return unique


def should_enforce_numbering(rel_path: str) -> bool:
    path: Path = Path(rel_path)
    if path.suffix == ".mdc":
        return True
    if path.name in STRUCTURE_EXEMPT_BASENAMES:
        return False
    if path.name in NUMBERED_SECTION_BASENAMES:
        return True
    return False


def check_filename(rel_path: str) -> list[Issue]:
    path: Path = Path(rel_path)
    if path.name in SPECIAL_FILENAMES:
        return []
    if FILENAME_PATTERN.match(path.name):
        return []
    return [
        Issue(
            path=rel_path,
            line=1,
            rule="file-name",
            message="文件名应使用小写英文 + 短横线，或使用约定保留名（如 README.md / PLAN.md）",
        )
    ]


def strip_inline_segments(line: str) -> str:
    no_code: str = INLINE_CODE_PATTERN.sub("", line)
    return URL_PATTERN.sub("", no_code)


def check_frontmatter_for_mdc(rel_path: str, lines: list[str]) -> list[Issue]:
    if not rel_path.endswith(".mdc"):
        return []

    issues: list[Issue] = []
    if not lines or lines[0].strip() != "---":
        issues.append(Issue(rel_path, 1, "mdc-frontmatter", ".mdc 文件必须以 YAML frontmatter 开头"))
        return issues

    try:
        closing_index: int = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration:
        issues.append(Issue(rel_path, 1, "mdc-frontmatter", ".mdc 文件缺少 frontmatter 结束分隔符 ---"))
        return issues

    frontmatter: str = "\n".join(lines[: closing_index + 1])
    if "description:" not in frontmatter:
        issues.append(Issue(rel_path, 1, "mdc-description", "frontmatter 缺少 description 字段"))
    if "globs:" not in frontmatter and "alwaysApply:" not in frontmatter:
        issues.append(Issue(rel_path, 1, "mdc-scope", "frontmatter 至少需要 globs 或 alwaysApply 之一"))
    return issues


def check_content(path: Path) -> list[Issue]:
    rel_path: str = path.relative_to(ROOT).as_posix()
    issues: list[Issue] = []
    issues.extend(check_filename(rel_path))

    try:
        content: str = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return [Issue(rel_path, 1, "encoding", f"文件不是 UTF-8 编码：{exc}")]

    if content and not content.endswith("\n"):
        issues.append(Issue(rel_path, max(content.count("\n"), 1), "trailing-newline", "文件末尾需要保留一个空行"))

    lines: list[str] = content.splitlines()
    issues.extend(check_frontmatter_for_mdc(rel_path, lines))

    in_fence: bool = False
    prev_heading_level: int = 0
    enforce_numbering: bool = should_enforce_numbering(rel_path)

    line_no: int
    line: str
    for line_no, line in enumerate(lines, start=1):
        fence_match: re.Match[str] | None = FENCE_PATTERN.match(line.strip())
        if line.strip().startswith("```"):
            if not in_fence:
                if fence_match is None or not fence_match.group(1):
                    issues.append(Issue(rel_path, line_no, "fence-language", "代码块必须标注语言类型"))
                in_fence = True
            else:
                in_fence = False
            continue

        if in_fence:
            continue

        stripped_for_spacing: str = strip_inline_segments(line)
        if ELLIPSIS_PATTERN.search(stripped_for_spacing):
            issues.append(Issue(rel_path, line_no, "ellipsis", "中文文档请使用 `⋯⋯`，不要使用 `...`"))

        if CJK_LATIN_PATTERN.search(stripped_for_spacing):
            issues.append(Issue(rel_path, line_no, "cjk-latin-spacing", "中英文之间需要保留空格"))

        heading_match: re.Match[str] | None = HEADING_PATTERN.match(line)
        if not heading_match:
            continue

        level: int = len(heading_match.group(1))
        title: str = heading_match.group(2).strip()
        if prev_heading_level and level > prev_heading_level + 1:
            issues.append(Issue(rel_path, line_no, "heading-level", "标题层级不能跳级"))
        prev_heading_level = level

        if " + " in title or " / " in title:
            issues.append(
                Issue(
                    rel_path,
                    line_no,
                    "concise-title",
                    "事项标题和总结性短语不要使用 `+`、`/` 拼接并列动作",
                )
            )

        if not enforce_numbering:
            continue
        if level == 2 and not re.match(r"^0x\d{2}\s+", title):
            issues.append(Issue(rel_path, line_no, "section-number", "二级标题应使用 `## 0x01 标题` 格式"))
        if level == 3 and not re.match(r"^[a-z]\.\s+", title):
            issues.append(Issue(rel_path, line_no, "subsection-format", "三级标题应使用 `### a. 标题` 格式"))

    return issues


def render_issues(issues: Iterable[Issue]) -> str:
    lines: list[str] = []
    issue: Issue
    for issue in issues:
        lines.append(f"{issue.path}:{issue.line}: [{issue.rule}] {issue.message}")
    return "\n".join(lines)


def main() -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description="检查 Markdown / MDC 文档规范")
    parser.add_argument("files", nargs="*", help="待检查文件列表；不传且加 --all 时检查全仓")
    parser.add_argument("--all", action="store_true", help="检查工作区内所有 .md / .mdc 文件")
    args: argparse.Namespace = parser.parse_args()

    try:
        targets: list[Path] = iter_target_files(args.files, args.all or not args.files)
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    if not targets:
        print("No Markdown or MDC files to check.")
        return 0

    all_issues: list[Issue] = []
    target: Path
    for target in targets:
        all_issues.extend(check_content(target))

    if all_issues:
        print(render_issues(all_issues))
        print()
        print(f"Doc style check failed: {len(all_issues)} issues in {len(targets)} files.")
        return 1

    print(f"Doc style check passed: {len(targets)} files checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
