#!/usr/bin/env python3
"""Inspect captured content before executing the original CLI."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import tomllib
from importlib import import_module
from pathlib import Path
from typing import Any

import scanner
from adapters import Blocked, Contents, Operation

ROOT: Path = Path(__file__).resolve().parent
ADAPTERS = {
    path.stem: import_module(f"adapters.{path.stem}")
    for path in (ROOT / "adapters").glob("[!_]*.py")
}


def merge_config(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Merge tables recursively; replace scalar and array values at the same key."""
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(defaults.get(key), dict):
            merge_config(defaults[key], value)
        else:
            defaults[key] = value
    return defaults


def load_config(path: Path | None = None) -> dict[str, Any]:
    data: dict[str, Any] = tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))
    if path is not None:
        merge_config(data, tomllib.loads(path.read_text(encoding="utf-8")))
    if set(data) != {"commands", "scan"}:
        raise ValueError("unknown_or_missing_config_sections")
    if not isinstance(data["commands"], dict) or not set(data["commands"]) <= set(ADAPTERS):
        raise ValueError("unknown_adapters")
    for tool, groups in data["commands"].items():
        adapter = ADAPTERS[tool]
        if not isinstance(groups, dict) or not set(groups) <= set(adapter.COMMANDS):
            raise ValueError("unknown_command_groups")
        for name, value in groups.items():
            depth: int = adapter.COMMANDS[name]
            if depth == 1:
                if type(value) is not bool:
                    raise ValueError("expected_command_switch")
            else:
                scanner.strings(value)
    return data


def selected(operation: Operation, scope: dict) -> bool:
    route: tuple[str, ...] = operation.route
    if route[0] not in scope:
        return False
    value: Any = scope[route[0]]
    return value if len(route) == 1 else route[1] in value


def run(tool: str, executable: str, args: list[str], config_path: Path | None = None) -> int:
    adapter = ADAPTERS[tool]
    operation: Operation | None = adapter.classify(args)
    if operation is None:
        return subprocess.call([executable, *args])
    config: dict[str, Any] = load_config(config_path)
    if tool not in config["commands"] or not selected(operation, config["commands"][tool]):
        return subprocess.call([executable, *args])
    policy: scanner.Policy = scanner.Policy.from_config(config["scan"])
    with tempfile.TemporaryDirectory(prefix="cli-guard-") as directory:
        contents: Contents = Contents(Path(directory))
        argv: list[str] = adapter.prepare(args, operation, contents)
        finding: scanner.Finding | None = scanner.inspect(contents.values, policy)
        if finding:
            raise Blocked(
                f"Sensitive content detected.\nLocation: {finding.field}:{finding.line}\n"
                f"Rule: {finding.rule}\n"
                "Action: Redact the indicated content, then retry the same command.",
                "sensitive_content",
            )
        return subprocess.call([executable, *argv])


def main() -> int:
    usage: str = "Usage: cli-guard [--config PATH] TOOL EXECUTABLE [ARG ...]"
    args: list[str] = sys.argv[1:]
    config_path: Path | None = None
    if args[:1] == ["--config"] and len(args) >= 2:
        config_path = Path(args[1])
        args = args[2:]
    if args in [["--help"], ["-h"]]:
        print(usage)
        print("Available adapters: " + ", ".join(sorted(ADAPTERS)))
        return 0
    list_tools: bool = args == ["--list-tools"]
    if not list_tools and (len(args) < 2 or args[0] not in ADAPTERS):
        print(usage, file=sys.stderr)
        return 2
    tool: str = "command" if list_tools else args[0]
    try:
        if list_tools:
            config: dict[str, Any] = load_config(config_path)
            scanner.Policy.from_config(config["scan"])
            print("\n".join(config["commands"]))
            return 0
        return run(tool, args[1], args[2:], config_path)
    except Blocked as error:
        message: str = f"BLOCKED [{error.code}]\n{error}"
        code: int = 1
    except scanner.ScanError as error:
        message = f"ERROR [scanner_failed]\n{error}"
        code = 2
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        message = (
            f"ERROR [check_failed]\nReason: {type(error).__name__}.\n"
            "Action: Check config.toml, input file paths and UTF-8 encoding, then retry."
        )
        code = 2
    name: str = tool if tool in ADAPTERS else "command"
    print(f"cli-guard: {message}\nOriginal {name} was not executed.", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
