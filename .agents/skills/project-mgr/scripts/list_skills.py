#!/usr/bin/env python3
"""Print absolute paths for skills declared by registered projects."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence


class ProjectSkillsError(ValueError):
    """Raised when a project skills declaration is invalid."""


def _registry_paths(workspace_root: Path) -> list[Path]:
    candidates: list[Path] = [
        workspace_root / "repos.json",
        workspace_root / "private" / "repos.json",
    ]
    return [path for path in candidates if path.is_file()]


def _load_projects(registry_path: Path) -> list[dict[str, Any]]:
    try:
        payload: Any = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProjectSkillsError(f"cannot read {registry_path}: {error}") from error

    if not isinstance(payload, list) or not all(
        isinstance(project, dict) for project in payload
    ):
        raise ProjectSkillsError(f"registry must contain a JSON array: {registry_path}")
    return payload


def _resolve_source_dir(project_root: Path, relative_dir: Any) -> Path:
    if not isinstance(relative_dir, str) or not relative_dir:
        raise ProjectSkillsError("skills[].dir must be a non-empty relative path")

    source_dir: Path = (project_root / relative_dir).resolve()
    try:
        source_dir.relative_to(project_root)
    except ValueError as error:
        raise ProjectSkillsError(
            f"skills[].dir must stay inside project local_path: {relative_dir}"
        ) from error
    if not source_dir.is_dir():
        raise ProjectSkillsError(f"skill directory does not exist: {source_dir}")
    return source_dir


def _resolve_source_skills(
    project_root: Path, source_config: dict[str, Any]
) -> list[Path]:
    source_dir: Path = _resolve_source_dir(project_root, source_config.get("dir"))
    configured_skills: Any = source_config.get("skills")

    if "skills" not in source_config or configured_skills == []:
        return sorted(
            (
                child.resolve()
                for child in source_dir.iterdir()
                if child.is_dir() and (child / "SKILL.md").is_file()
            ),
            key=lambda path: path.name,
        )

    if not isinstance(configured_skills, list):
        raise ProjectSkillsError(
            "skills[].skills must be an array; omit it to scan the directory"
        )

    skill_paths: list[Path] = []
    for skill_name in configured_skills:
        if not isinstance(skill_name, str) or not skill_name:
            raise ProjectSkillsError("skills[].skills entries must be non-empty strings")
        skill_path: Path = (source_dir / skill_name).resolve()
        try:
            skill_path.relative_to(source_dir)
        except ValueError as error:
            raise ProjectSkillsError(
                f"skill name must stay inside skills[].dir: {skill_name}"
            ) from error
        if not skill_path.is_dir() or not (skill_path / "SKILL.md").is_file():
            raise ProjectSkillsError(
                f"skill must contain SKILL.md: {skill_path}"
            )
        skill_paths.append(skill_path)
    return skill_paths


def list_skill_paths(workspace_root: Path) -> list[Path]:
    """Resolve all project skill paths from public and private registries."""

    root: Path = workspace_root.expanduser().resolve()
    registries: list[Path] = _registry_paths(root)
    if not registries:
        raise ProjectSkillsError(f"repos.json was not found under {root}")

    paths: list[Path] = []
    seen_paths: set[Path] = set()
    for registry_path in registries:
        for project in _load_projects(registry_path):
            source_configs: Any = project.get("skills")
            if source_configs is None:
                continue
            if not isinstance(source_configs, list):
                raise ProjectSkillsError(
                    f"project skills must be an array in {registry_path}"
                )

            local_path: Any = project.get("local_path")
            if not isinstance(local_path, str) or not local_path:
                raise ProjectSkillsError(
                    f"project with skills must define local_path in {registry_path}"
                )
            project_root: Path = Path(local_path).expanduser().resolve()
            if not project_root.is_dir():
                raise ProjectSkillsError(
                    f"project local_path does not exist: {project_root}"
                )

            for source_config in source_configs:
                if not isinstance(source_config, dict):
                    raise ProjectSkillsError("project skills entries must be objects")
                for skill_path in _resolve_source_skills(project_root, source_config):
                    if skill_path not in seen_paths:
                        paths.append(skill_path)
                        seen_paths.add(skill_path)
    return paths


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print one registered project skill absolute path per line."
    )
    parser.add_argument(
        "workspace_root",
        nargs="?",
        type=Path,
        default=Path.cwd(),
        help="workspace containing repos.json and private/repos.json",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args: argparse.Namespace = _parse_args(argv)
    try:
        for skill_path in list_skill_paths(args.workspace_root):
            print(skill_path)
    except ProjectSkillsError as error:
        print(f"project-mgr: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
