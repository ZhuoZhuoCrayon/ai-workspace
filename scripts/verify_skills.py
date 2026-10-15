#!/usr/bin/env python3
"""Report broken skill links and skills whose source is not declared."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR: Path = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / ".agents" / "skills" / "project-mgr"))

from scripts.registry import RegistryError, load, skill_paths  # noqa: E402


def _lock_names(workspace_root: Path) -> set[str]:
    lock_path: Path = workspace_root / "skills-lock.json"
    if not lock_path.is_file():
        return set()
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    skills = payload.get("skills", {})
    return set(skills) if isinstance(skills, dict) else set()


def _tracked_names(workspace_root: Path) -> set[str]:
    gitignore: Path = workspace_root / ".agents" / ".gitignore"
    names: set[str] = set()
    if not gitignore.is_file():
        return names
    for line in gitignore.read_text(encoding="utf-8").splitlines():
        text: str = line.strip()
        if text.startswith("!skills/") and text.endswith("/"):
            names.add(text.removeprefix("!skills/").strip("/"))
    return names


def verify(workspace_root: Path) -> int:
    """Return 2 when a link is broken. Unknown sources only warn."""

    root: Path = workspace_root.resolve()
    skills_dir: Path = root / ".agents" / "skills"
    broken: list[Path] = []
    for link in skills_dir.glob("*"):
        if link.is_symlink() and not link.exists():
            broken.append(link)
            print(f"verify: broken link {link}", file=sys.stderr)

    declared: set[str] = {path.name for path in skill_paths(load(root))}
    declared.update(_lock_names(root))
    declared.update(_tracked_names(root))
    for child in skills_dir.iterdir():
        if child.name not in declared:
            print(f"verify: unknown skill source {child.name}", file=sys.stderr)
    for entry in load(root):
        if entry.self_entry:
            continue
        if not entry.project_dir().is_dir():
            print(f"verify: missing project {entry.key}", file=sys.stderr)
    missing_external: set[str] = _lock_names(root) - {child.name for child in skills_dir.iterdir()}
    for name in sorted(missing_external):
        print(f"verify: locked skill is not installed {name}", file=sys.stderr)
    return 2 if broken else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify workspace skill sources.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        return verify(args.root)
    except RegistryError as error:
        print(f"verify: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
