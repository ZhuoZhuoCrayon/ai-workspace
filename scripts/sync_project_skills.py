#!/usr/bin/env python3
"""同步项目技能，并清理改名或取消注册后留下的受管软链接。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

WORKSPACE_ROOT: Path = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE_ROOT / ".agents/skills/project-mgr"))

from scripts.registry import RegistryError, load  # noqa: E402


def sync_links(root: Path, skills_dir: Path, registry_script: Path) -> None:
    """校验完整来源清单后更新链接，不删除普通目录或非项目软链接。"""
    entries = load(root)
    source_roots: list[Path] = [
        (entry.project_dir() / source["dir"]).resolve()
        for entry in entries
        for source in entry.skills
        if isinstance(source, dict) and isinstance(source.get("dir"), str)
    ]
    result: subprocess.CompletedProcess[str] = subprocess.run(
        [sys.executable, str(registry_script), "--root", str(root), "skills"],
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    expected: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        source: Path = Path(line).resolve()
        if not (source / "SKILL.md").is_file():
            raise RegistryError(f"skill must contain SKILL.md: {source}")
        if source.name in expected and expected[source.name] != str(source):
            raise RegistryError(f"duplicate project skill name: {source.name}")
        expected[source.name] = str(source)
        destination: Path = skills_dir / source.name
        if destination.exists() and not destination.is_symlink():
            raise RegistryError(f"cannot link project skill over directory: {destination}")

    state_path: Path = skills_dir.parent / ".project-skills.json"
    previous: dict[str, Any] = {}
    if state_path.exists():
        previous = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(previous, dict):
            raise RegistryError(f"invalid project skills state: {state_path}")

    skills_dir.mkdir(parents=True, exist_ok=True)
    for name, target in expected.items():
        destination = skills_dir / name
        if destination.is_symlink():
            if destination.resolve() == Path(target):
                continue
            destination.unlink()
        destination.symlink_to(target, target_is_directory=True)
        print(f"Linked project skill {name} -> {target}")

    for link in skills_dir.iterdir():
        if not link.is_symlink() or link.name in expected:
            continue
        resolved: Path = link.resolve()
        managed: bool = previous.get(link.name) == str(resolved) or any(
            resolved.is_relative_to(source_root) for source_root in source_roots
        )
        if managed:
            link.unlink()
            print(f"Removed stale project skill {link.name}")

    temporary_state: Path = state_path.with_suffix(".json.tmp")
    temporary_state.write_text(
        json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary_state.replace(state_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--skills-dir", type=Path, default=Path(".agents/skills"))
    parser.add_argument(
        "--registry-script", type=Path,
        default=Path(".agents/skills/project-mgr/scripts/registry.py"),
    )
    args = parser.parse_args()
    root: Path = args.root.resolve()
    try:
        sync_links(root, root / args.skills_dir, root / args.registry_script)
    except (RegistryError, OSError, ValueError, subprocess.CalledProcessError) as error:
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr, end="")
        print(f"skills: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
