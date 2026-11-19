#!/usr/bin/env python3
"""发布前检查 review 评论格式：一条 finding 一个 Markdown 文件，文件内容即发布正文。"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

HEADER_PATTERN = re.compile(r"^\*\*`[^`\s]+:\d+`\*\* \[P[0-2]\]$")
FENCE_PATTERN = re.compile(r"^\s{0,3}(?P<fence>`{3,}|~{3,})")
LINK_PATTERN = re.compile(r"\[([^\]\n]*)\]\([^)\n]*\)")
CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
WORD_PATTERN = re.compile(r"[A-Za-z0-9_]+(?:[.'-][A-Za-z0-9_]+)*")

SHORT_REVIEW_LIMIT = 15
CODE_LINES_WARNING = 30


@dataclass
class CodeBlock:
    start: int
    lines: list[str] = field(default_factory=list)
    closed: bool = False


@dataclass
class Report:
    path: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def split_code_blocks(lines: list[str]) -> tuple[list[str], list[CodeBlock]]:
    """拆出围栏代码块，返回代码块外的正文行与代码块。"""
    prose: list[str] = []
    blocks: list[CodeBlock] = []
    opening: str | None = None
    for number, line in enumerate(lines, start=1):
        match = FENCE_PATTERN.match(line)
        if opening is None:
            if match:
                opening = match.group("fence")
                blocks.append(CodeBlock(start=number))
            else:
                prose.append(line)
            continue
        fence = match.group("fence") if match else ""
        if fence and fence[0] == opening[0] and len(fence) >= len(opening) and not line.strip()[len(fence) :]:
            blocks[-1].closed = True
            opening = None
        else:
            blocks[-1].lines.append(line)
    return prose, blocks


def count_text_units(lines: list[str]) -> int:
    """统计正文长度：中文按字符计，英文和数字按单词计；链接只计标题，不计 URL。"""
    text = LINK_PATTERN.sub(r"\1", "\n".join(lines))
    return len(CJK_PATTERN.findall(text)) + len(WORD_PATTERN.findall(text))


def check_comment(path: Path) -> Report:
    report = Report(path=path)
    lines = path.read_text(encoding="utf-8").splitlines()
    content_indexes = [index for index, line in enumerate(lines) if line.strip()]
    if not content_indexes:
        report.errors.append("评论为空")
        return report

    header = lines[content_indexes[0]].strip()
    if not HEADER_PATTERN.match(header):
        report.errors.append(f"首行应为 **`path:line`** [P0|P1|P2]，实际为：{header[:80]}")

    body_start = content_indexes[0] + 1
    if len(content_indexes) > 1 and lines[content_indexes[1]].lstrip().startswith(">"):
        body_start = content_indexes[1]
        while body_start < len(lines) and lines[body_start].lstrip().startswith(">"):
            body_start += 1
    else:
        report.errors.append("第二个非空行应为 > 引用的问题代码")

    prose, blocks = split_code_blocks(lines[body_start:])
    for block in blocks:
        line_number = body_start + block.start
        if not block.closed:
            report.errors.append(f"第 {line_number} 行的代码块未闭合")
        elif not any(line.strip() for line in block.lines):
            report.errors.append(f"第 {line_number} 行的代码块为空")
        elif len(block.lines) > CODE_LINES_WARNING:
            report.warnings.append(
                f"第 {line_number} 行的代码块有 {len(block.lines)} 行，确认仍是核心伪代码而非完整实现"
            )

    text_units = count_text_units(prose)
    if text_units == 0:
        report.errors.append("缺少问题与建议正文")
    elif not blocks and text_units >= SHORT_REVIEW_LIMIT:
        report.errors.append(
            f"缺少核心伪代码块：正文 {text_units} 个字/词，只有少于 {SHORT_REVIEW_LIMIT} 的极短 review 可省略"
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="+", help="评论文件或目录；目录下的 *.md 各为一条 finding")
    args = parser.parse_args(argv)

    files: list[Path] = []
    for target in map(Path, args.targets):
        if not target.exists():
            parser.error(f"路径不存在：{target}")
        files.extend(sorted(target.glob("*.md")) if target.is_dir() else [target])
    if not files:
        parser.error("没有找到评论文件")

    failed = 0
    for report in map(check_comment, files):
        status = "FAIL" if report.errors else "PASS"
        failed += bool(report.errors)
        print(f"[{status}] {report.path}")
        for message in report.errors:
            print(f"  - {message}")
        for message in report.warnings:
            print(f"  ! {message}")

    print(f"{len(files) - failed}/{len(files)} 条评论通过检查")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
