#!/usr/bin/env python3
"""补齐外部技能锁文件的 GitHub 克隆地址，兼容只记录 owner/repo 的旧条目。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def normalize_sources(root: Path) -> int:
    lock_path: Path = root / "skills-lock.json"
    payload: dict[str, Any] = json.loads(lock_path.read_text(encoding="utf-8"))
    skills: Any = payload.get("skills")
    if not isinstance(skills, dict):
        raise ValueError("skills-lock.json skills must be an object")
    changed: int = 0
    for name, entry in skills.items():
        if not isinstance(entry, dict):
            raise ValueError(f"invalid skill lock entry: {name}")
        if entry.get("sourceType") != "github" or entry.get("sourceUrl"):
            continue
        source: Any = entry.get("source")
        if not isinstance(source, str) or not re.fullmatch(r"[\w.-]+/[\w.-]+", source):
            raise ValueError(f"invalid GitHub source for skill {name}")
        entry["sourceUrl"] = f"https://github.com/{source}.git"
        changed += 1
    if changed:
        temporary: Path = lock_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(lock_path)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        changed: int = normalize_sources(args.root)
    except (OSError, ValueError, TypeError, AttributeError) as error:
        print(f"skills: {error}", file=sys.stderr)
        return 2
    if changed:
        print(f"Normalized clone URLs for {changed} external skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
