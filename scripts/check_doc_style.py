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
MAX_PROSE_LINE_LENGTH = 120

LOWERCASE_FILENAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\.(md|mdc)$")
UPPERCASE_MD_FILENAME = re.compile(r"^[A-Z0-9]+\.md$")

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
H2_NUMBERING = re.compile(r"^0x\d{2}\s+")
H3_NUMBERING = re.compile(r"^[a-z]\.\s+")
TABLE_SEPARATOR_PATTERN = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")
INLINE_CODE_PATTERN = re.compile(r"`[^`]*`")
LIST_ITEM_PATTERN = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")
TABLE_CELL_SPLIT_PATTERN = re.compile(r"(?<!\\)\|")
TABLE_CELL_BREAK_PATTERN = re.compile(r"<br\s*/?>", re.IGNORECASE)
TABLE_CELL_END_PUNCT_PATTERN = re.compile(r"[。！？!?]")
PROSE_END_PUNCT_PATTERN = re.compile(r"[。！？!?]")


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


def get_frontmatter_lines(lines: list[str]) -> set[int]:
    if not lines or lines[0].strip() != "---":
        return set()
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return set(range(1, index + 2))
    return set()


def is_table_line(stripped: str) -> bool:
    return stripped.startswith("|") or TABLE_SEPARATOR_PATTERN.match(stripped) is not None


def is_url_only_line(stripped: str) -> bool:
    return stripped.startswith("http://") or stripped.startswith("https://") or (
        stripped.startswith("<http://") or stripped.startswith("<https://")
    )


def strip_inline_code(line: str) -> str:
    return INLINE_CODE_PATTERN.sub("", line)


def iter_prose_blocks(lines: list[str], frontmatter_lines: set[int]) -> list[tuple[int, list[str], str]]:
    blocks: list[tuple[int, list[str], str]] = []
    in_fence = False
    current_lines: list[str] = []
    start_line = 0

    def flush() -> None:
        nonlocal current_lines, start_line
        if not current_lines:
            return
        text = " ".join(strip_inline_code(line).strip() for line in current_lines).strip()
        if text:
            blocks.append((start_line, current_lines[:], text))
        current_lines = []
        start_line = 0

    for line_no, line in enumerate(lines, start=1):
        if line_no in frontmatter_lines:
            flush()
            continue
        if line.strip().startswith("```"):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if is_table_line(stripped) or HEADING_PATTERN.match(line):
            flush()
            continue
        if LIST_ITEM_PATTERN.match(line):
            flush()
            current_lines = [line]
            start_line = line_no
            continue

        if not current_lines:
            current_lines = [line]
            start_line = line_no
            continue

        current_lines.append(line)

    flush()
    return blocks


def split_table_cells(line: str) -> list[str]:
    parts: list[str] = TABLE_CELL_SPLIT_PATTERN.split(line.strip())
    if parts and not parts[0].strip():
        parts = parts[1:]
    if parts and not parts[-1].strip():
        parts = parts[:-1]
    return [part.strip() for part in parts if part.strip()]


def split_table_cell_segments(cell: str) -> list[str]:
    return [segment.strip() for segment in TABLE_CELL_BREAK_PATTERN.split(cell) if segment.strip()]


def iter_table_cells(lines: list[str], frontmatter_lines: set[int]) -> list[tuple[int, str]]:
    cells: list[tuple[int, str]] = []
    in_fence = False

    for line_no, line in enumerate(lines, start=1):
        if line_no in frontmatter_lines:
            continue
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        stripped = line.strip()
        if not stripped or not is_table_line(stripped):
            continue
        if TABLE_SEPARATOR_PATTERN.match(stripped) is not None:
            continue

        for cell in split_table_cells(line):
            cell_text = strip_inline_code(cell).strip()
            if cell_text:
                cells.append((line_no, cell_text))
    return cells


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

    frontmatter_lines = get_frontmatter_lines(lines)
    in_fence = False
    for line_no, line in enumerate(lines, start=1):
        if line_no in frontmatter_lines:
            continue
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        stripped = line.strip()
        prose = strip_inline_code(line)
        prose_stripped = prose.strip()
        is_table = is_table_line(stripped)
        if prose_stripped:
            if (
                len(line) > MAX_PROSE_LINE_LENGTH
                and not is_table
                and not is_url_only_line(stripped)
            ):
                issues.append(
                    Issue(
                        rel_path,
                        line_no,
                        "line-too-long",
                        f"单行避免过长，请控制在 {MAX_PROSE_LINE_LENGTH} 个字符内，或拆行改写",
                    )
                )

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

    for line_no, source_lines, block in iter_prose_blocks(lines, frontmatter_lines):
        if block.count("。") >= 2:
            issues.append(
                Issue(
                    rel_path,
                    line_no,
                    "sentence-split-period",
                    "同一 Markdown 段落或列表项里不要出现两个句号，请拆分",
                )
            )
        if ";" in block or "；" in block:
            issues.append(
                Issue(
                    rel_path,
                    line_no,
                    "sentence-split-semicolon",
                    "同一 Markdown 段落或列表项里不要出现分号，请改成分句、列表或拆段",
                )
            )
        raw_block = " ".join(line.strip() for line in source_lines).strip()
        end_punct_count = len(PROSE_END_PUNCT_PATTERN.findall(block))
        if len(source_lines) > 1 and len(raw_block) <= MAX_PROSE_LINE_LENGTH and end_punct_count <= 1:
            issues.append(
                Issue(
                    rel_path,
                    line_no,
                    "single-sentence-soft-wrap",
                    f"单句内容合并后不超过 {MAX_PROSE_LINE_LENGTH} 个字符时，不要拆成多行",
                )
            )

    table_semicolon_lines: set[int] = set()
    table_multi_end_punct_lines: set[int] = set()
    for line_no, cell in iter_table_cells(lines, frontmatter_lines):
        if (";" in cell or "；" in cell) and line_no not in table_semicolon_lines:
            table_semicolon_lines.add(line_no)
            issues.append(
                Issue(
                    rel_path,
                    line_no,
                    "table-cell-semicolon",
                    "表格单元格内不要出现分号，请改成换行、列表或表格外脚注",
                )
            )
        if line_no in table_multi_end_punct_lines:
            continue
        for segment in split_table_cell_segments(cell):
            if len(TABLE_CELL_END_PUNCT_PATTERN.findall(segment)) >= 2:
                table_multi_end_punct_lines.add(line_no)
                issues.append(
                    Issue(
                        rel_path,
                        line_no,
                        "table-cell-multi-end-punct",
                        "表格单元格未分段时不要出现多个结束符，请改成 `<br />` 编号或表格外脚注",
                    )
                )
                break
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
