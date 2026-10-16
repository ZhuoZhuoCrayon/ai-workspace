#!/usr/bin/env python3
"""Resolve registered project directories and clone missing repositories."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse


class RegistryError(ValueError):
    """Raised when a registry declaration is invalid."""


@dataclass
class Entry:
    """One project declared in a public or private registry."""

    name: str
    key: str
    git_url: str
    branch: str
    local_path: str
    subdir: str
    language: str
    self_entry: bool
    user_name: str = ""
    user_email: str = ""
    skills: list[Any] = field(default_factory=list)
    workspace_root: Path = field(repr=False, default_factory=Path.cwd)
    projects_root: Path = field(repr=False, default_factory=Path.home)
    overrides: dict[str, str] = field(repr=False, default_factory=dict)

    def clone_dir(self) -> Path:
        """Return the repository checkout directory."""

        if self.self_entry:
            return self.workspace_root
        override: str | None = self.overrides.get(self.key)
        if override:
            return Path(override).expanduser()
        return self.projects_root / self.local_path

    def project_dir(self) -> Path:
        """Return the project directory inside the repository."""

        return self.clone_dir() / self.subdir


def normalize_git_url(git_url: str) -> str:
    """Reduce a Git URL to ``host/owner/repo`` for identity comparison."""

    text: str = git_url.strip()
    if text.startswith("git@"):
        host, _, path = text[4:].partition(":")
        parts: list[str] = [host, path]
    else:
        parsed = urlparse(text)
        parts = [parsed.hostname or "", parsed.path]
    text = "/".join(part.strip("/") for part in parts if part.strip("/"))
    return text.removesuffix(".git").lower()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RegistryError(f"cannot read {path}: {error}") from error


def _projects_root(workspace_root: Path, local: dict[str, Any]) -> Path:
    configured: str | None = os.environ.get("PROJECTS_ROOT")
    if not configured:
        raw: Any = local.get("projects_root")
        configured = raw if isinstance(raw, str) and raw else "~/Project"
    return Path(configured).expanduser()


def _git_identity(payload: dict[str, Any], *, private: bool, name: str) -> tuple[str, str]:
    """Return optional Git author fields. Private entries may set both or neither."""

    has_name: bool = "user_name" in payload
    has_email: bool = "user_email" in payload
    if not private and (has_name or has_email):
        raise RegistryError(f"{name}: user_name and user_email belong to the private registry")
    raw_name: Any = payload.get("user_name", "")
    raw_email: Any = payload.get("user_email", "")
    if raw_name is None:
        raw_name = ""
    if raw_email is None:
        raw_email = ""
    if not isinstance(raw_name, str) or not isinstance(raw_email, str):
        raise RegistryError(f"{name}: user_name and user_email must be strings")
    user_name: str = raw_name.strip()
    user_email: str = raw_email.strip()
    if bool(user_name) != bool(user_email):
        raise RegistryError(f"{name}: user_name and user_email must be set together")
    if any(char in user_name for char in "\r\n"):
        raise RegistryError(f"{name}: user_name is invalid")
    local: str
    separator: str
    domain: str
    local, separator, domain = user_email.partition("@")
    email_ok: bool = bool(separator and local and "." in domain and "@" not in domain and " " not in user_email)
    if user_email and not email_ok:
        raise RegistryError(f"{name}: user_email is invalid")
    return user_name, user_email


def _overrides(local: dict[str, Any]) -> dict[str, str]:
    projects: Any = local.get("projects", {})
    if not isinstance(projects, dict):
        raise RegistryError("repos.local.json projects must be an object")
    overrides: dict[str, str] = {}
    for key, value in projects.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise RegistryError(f"invalid project override: {key}")
        if not value.startswith(("/", "~")):
            raise RegistryError(f"project override must be absolute: {key}")
        overrides[key] = value
    return overrides


def _entry_from_payload(
    payload: dict[str, Any],
    *,
    private: bool,
    workspace_root: Path,
    projects_root: Path,
    overrides: dict[str, str],
) -> Entry:
    name: Any = payload.get("name")
    if not isinstance(name, str) or not name:
        raise RegistryError("project name must be a non-empty string")
    self_entry: bool = payload.get("self") is True
    local_path: Any = payload.get("local_path", "")
    if not self_entry:
        if not isinstance(local_path, str) or not local_path:
            raise RegistryError(f"{name}: local_path is required")
        if local_path.startswith(("/", "~")):
            raise RegistryError(f"{name}: local_path must be relative")
    skills: Any = payload.get("skills", [])
    if skills is None:
        skills = []
    if not isinstance(skills, list):
        raise RegistryError(f"{name}: skills must be an array")
    user_name, user_email = _git_identity(payload, private=private, name=name)
    return Entry(
        name=name,
        key=f"private/{name}" if private else name,
        git_url=str(payload.get("git_url") or ""),
        branch=str(payload.get("branch") or ""),
        local_path="" if self_entry else str(local_path),
        subdir=str(payload.get("subdir") or "."),
        language=str(payload.get("language") or "zh"),
        self_entry=self_entry,
        user_name=user_name,
        user_email=user_email,
        skills=skills,
        workspace_root=workspace_root,
        projects_root=projects_root,
        overrides=overrides,
    )


def _load_registry(path: Path, private: bool, **context: Any) -> list[Entry]:
    if not path.is_file():
        return []
    payload: Any = _read_json(path)
    if not isinstance(payload, list):
        raise RegistryError(f"registry must contain a JSON array: {path}")
    return [
        _entry_from_payload(item, private=private, **context)
        for item in payload
        if isinstance(item, dict)
    ]


def _context(workspace_root: Path) -> dict[str, Any]:
    local_path: Path = workspace_root / "repos.local.json"
    local: dict[str, Any] = {}
    if local_path.is_file():
        payload: Any = _read_json(local_path)
        if not isinstance(payload, dict):
            raise RegistryError("repos.local.json must be an object")
        local = payload
    return {
        "workspace_root": workspace_root,
        "projects_root": _projects_root(workspace_root, local),
        "overrides": _overrides(local),
    }


def load(workspace_root: Path, *, include_private: bool = True) -> list[Entry]:
    """Load registries and reject declarations that cannot be resolved."""

    root: Path = workspace_root.expanduser().resolve()
    context: dict[str, Any] = _context(root)
    entries: list[Entry] = _load_registry(root / "repos.json", False, **context)
    if include_private:
        entries.extend(_load_registry(root / "private" / "repos.json", True, **context))

    if include_private:
        self_count: int = sum(entry.self_entry for entry in entries)
        if self_count != 1:
            raise RegistryError(f"self entry count must be 1, got {self_count}")

    seen: dict[Path, str] = {}
    for entry in entries:
        if entry.self_entry:
            continue
        clone_dir: Path = entry.clone_dir()
        identity: str = normalize_git_url(entry.git_url)
        previous: str | None = seen.get(clone_dir)
        if previous is not None and previous != identity:
            raise RegistryError(f"clone directory conflict: {clone_dir}")
        seen[clone_dir] = identity
    return entries


def find(entries: Sequence[Entry], key: str) -> Entry:
    """Return the entry for a public name or ``private/<name>`` key."""

    for entry in entries:
        if entry.key == key:
            return entry
    raise RegistryError(f"project not found: {key}")


def _resolve_source_dir(project_root: Path, relative_dir: Any) -> Path:
    if not isinstance(relative_dir, str) or not relative_dir:
        raise RegistryError("skills[].dir must be a non-empty relative path")
    source_dir: Path = (project_root / relative_dir).resolve()
    try:
        source_dir.relative_to(project_root.resolve())
    except ValueError as error:
        raise RegistryError(
            f"skills[].dir must stay inside project directory: {relative_dir}"
        ) from error
    return source_dir


def skill_paths(entries: Sequence[Entry]) -> list[Path]:
    """Resolve project skill directories, skipping ones that are absent."""

    paths: list[Path] = []
    seen: set[Path] = set()
    for entry in entries:
        if not entry.skills:
            continue
        project_root: Path = entry.project_dir()
        if not project_root.is_dir():
            print(f"registry: skip missing project {entry.key}", file=sys.stderr)
            continue
        for source in entry.skills:
            if not isinstance(source, dict):
                raise RegistryError(f"{entry.key}: skills entries must be objects")
            source_dir: Path = _resolve_source_dir(project_root, source.get("dir"))
            if not source_dir.is_dir():
                print(f"registry: skip missing skill dir {source_dir}", file=sys.stderr)
                continue
            configured: Any = source.get("skills")
            if "skills" not in source or configured == []:
                candidates: list[Path] = sorted(
                    (
                        child
                        for child in source_dir.iterdir()
                        if child.is_dir() and (child / "SKILL.md").is_file()
                    ),
                    key=lambda path: path.name,
                )
            else:
                if not isinstance(configured, list):
                    raise RegistryError(f"{entry.key}: skills[].skills must be an array")
                candidates = []
                for name in configured:
                    skill_path: Path = source_dir / str(name)
                    if skill_path.is_dir() and (skill_path / "SKILL.md").is_file():
                        candidates.append(skill_path)
                    else:
                        print(f"registry: skip missing skill {skill_path}", file=sys.stderr)
            for skill_path in candidates:
                resolved: Path = skill_path.resolve()
                if resolved not in seen:
                    paths.append(resolved)
                    seen.add(resolved)
    return paths


def _git_clone(url: str, branch: str, destination: Path) -> None:
    command: list[str] = ["git", "clone"]
    if branch:
        command.extend(["--branch", branch])
    command.extend([url, str(destination)])
    environment: dict[str, str] = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"
    subprocess.run(command, check=True, env=environment)


def sync(workspace_root: Path) -> list[tuple[str, str, str]]:
    """Clone missing repositories. Existing directories stay untouched."""

    root: Path = workspace_root.expanduser().resolve()
    results: list[tuple[str, str, str]] = []
    public: list[Entry] = load(root, include_private=False)
    private_entry: Entry | None = next(
        (entry for entry in public if entry.name == "ai-workspace-private"), None
    )
    private_dir: Path = root / "private"
    if private_dir.exists():
        results.append(("private-repo", "present", str(private_dir)))
    elif private_entry is None or not private_entry.git_url:
        results.append(("private-repo", "skipped", "no git_url"))
    else:
        try:
            _git_clone(private_entry.git_url, private_entry.branch, private_dir)
            results.append(("private-repo", "cloned", str(private_dir)))
        except subprocess.CalledProcessError as error:
            results.append(("private-repo", "failed", str(error.returncode)))

    cloned_dirs: set[Path] = set()
    for entry in load(root):
        if entry.self_entry:
            continue
        destination: Path = entry.clone_dir()
        if destination in cloned_dirs or destination.exists():
            state: str = "present"
            detail: str = str(destination)
            if destination in cloned_dirs:
                detail = "shared clone"
            results.append((entry.key, state, detail))
            cloned_dirs.add(destination)
            continue
        if not entry.git_url:
            results.append((entry.key, "skipped", "no git_url"))
            continue
        try:
            _git_clone(entry.git_url, entry.branch, destination)
            results.append((entry.key, "cloned", str(destination)))
            cloned_dirs.add(destination)
        except subprocess.CalledProcessError as error:
            results.append((entry.key, "failed", str(error.returncode)))
    return results


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve and clone workspace projects.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    path_parser = subparsers.add_parser("path")
    path_parser.add_argument("key")

    subparsers.add_parser("skills")
    subparsers.add_parser("sync")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args: argparse.Namespace = _parse_args(argv)
    try:
        if args.command == "path":
            entry: Entry = find(load(args.root), args.key)
            print(f"{entry.project_dir()}\t{entry.language}")
        elif args.command == "skills":
            for skill_path in skill_paths(load(args.root)):
                print(skill_path)
        elif args.command == "sync":
            rows: list[tuple[str, str, str]] = sync(args.root)
            counts: dict[str, int] = {}
            for key, state, detail in rows:
                counts[state] = counts.get(state, 0) + 1
                print(f"{key}\t{state}\t{detail}")
            summary: str = "\t".join(f"{state}={count}" for state, count in sorted(counts.items()))
            print(summary)
    except RegistryError as error:
        print(f"registry: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
