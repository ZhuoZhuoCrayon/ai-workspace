#!/usr/bin/env python3
"""Workspace-specific checks for Markdown and MDC documents."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_SUFFIXES = {".md", ".mdc"}
EXCLUDED_PARTS = {".git", "node_modules", "__pycache__", ".venv", "venv"}

LOWERCASE_FILENAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\.(md|mdc)$")
UPPERCASE_MD_FILENAME = re.compile(r"^[A-Z0-9]+\.md$")

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
H2_NUMBERING = re.compile(r"^0x\d{2}\s+")
H3_NUMBERING = re.compile(r"^[a-z]\.\s+")


@dataclass(frozen=True)
class Issue:
    file: str
    line: int
    rule: str
    message: str

    def render(self) -> str:
        return f"{self.file}:{self.line}: [{self.rule}] {self.message}"


def iter_targets(files: list[str], scan_all: bool) -> list[Path]:
    if files:
        candidates = []
        for raw in files:
            path = Path(raw)
            if not path.is_absolute():
                path = ROOT / path
            if path.is_file():
                candidates.append(path.resolve())
    elif scan_all:
        candidates = [path.resolve() for path in ROOT.rglob("*") if path.is_file()]
    else:
        raise ValueError("Must provide files or use --all")

    selected: list[Path] = []
    seen: set[Path] = set()
    for path in sorted(candidates):
        if path in seen:
            continue
        seen.add(path)
        if path.suffix not in DOC_SUFFIXES:
            continue
        if any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        selected.append(path)
    return selected


def check_mdc_frontmatter(lines: list[str], rel_path: str) -> list[Issue]:
    issues: list[Issue] = []
    if not lines or lines[0].strip() != "---":
        issues.append(Issue(rel_path, 1, "mdc-frontmatter", ".mdc 文件必须以 YAML frontmatter 开头"))
        return issues
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration:
        issues.append(Issue(rel_path, 1, "mdc-frontmatter", ".mdc 文件缺少 frontmatter 结束分隔符 ---"))
        return issues

    frontmatter = "\n".join(lines[: end + 1])
    if "description:" not in frontmatter:
        issues.append(Issue(rel_path, 1, "mdc-description", "frontmatter 缺少 description 字段"))
    if "globs:" not in frontmatter and "alwaysApply:" not in frontmatter:
        issues.append(Issue(rel_path, 1, "mdc-scope", "frontmatter 至少需要 globs 或 alwaysApply 之一"))
    return issues


def check_file(path: Path) -> list[Issue]:
    rel_path = path.relative_to(ROOT).as_posix()
    issues: list[Issue] = []

    if not (LOWERCASE_FILENAME.fullmatch(path.name) or UPPERCASE_MD_FILENAME.fullmatch(path.name)):
        issues.append(Issue(rel_path, 1, "file-name", "文件名应为小写短横线，或全大写约定名（如 README.md）"))

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return [Issue(rel_path, 1, "encoding", f"文件不是 UTF-8 编码：{exc}")]

    lines = content.splitlines()
    if path.suffix == ".mdc":
        issues.extend(check_mdc_frontmatter(lines, rel_path))

    in_fence = False
    for line_no, line in enumerate(lines, start=1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        heading = HEADING_PATTERN.match(line)
        if heading is None:
            continue

        level = len(heading.group(1))
        title = heading.group(2).strip()
        if " + " in title or " / " in title:
            issues.append(Issue(rel_path, line_no, "concise-title", "事项标题和总结性短语不要使用 `+`、`/` 拼接并列动作"))
        if level == 2 and H2_NUMBERING.match(title) is None:
            issues.append(Issue(rel_path, line_no, "section-number", "二级标题应使用 `## 0x01 标题` 格式"))
        if level == 3 and H3_NUMBERING.match(title) is None:
            issues.append(Issue(rel_path, line_no, "subsection-format", "三级标题应使用 `### a. 标题` 格式"))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 Markdown / MDC 文档规范")
    parser.add_argument("files", nargs="*", help="待检查文件列表；不传且加 --all 时检查全仓")
    parser.add_argument("--all", action="store_true", help="检查工作区内所有 .md / .mdc 文件")
    args = parser.parse_args()

    targets = iter_targets(args.files, args.all or not args.files)
    if not targets:
        print("No Markdown or MDC files to check.")
        return 0

    issues = [issue for target in targets for issue in check_file(target)]
    if issues:
        print("\n".join(issue.render() for issue in issues))
        print(f"\nDoc style check failed: {len(issues)} issues in {len(targets)} files.")
        return 1

    print(f"Doc style check passed: {len(targets)} files checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
