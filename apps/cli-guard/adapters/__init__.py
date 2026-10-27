"""Shared CLI parsing and payload capture; no scanning or command execution."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, NamedTuple

FALSE_VALUES: set[str] = {"0", "f", "F", "false", "False", "FALSE"}


class Blocked(Exception):
    """The command cannot proceed with uninspectable or sensitive content."""

    def __init__(self, message: str, code: str = "uninspectable_content") -> None:
        super().__init__(message)
        self.code = code


class Argument(NamedTuple):
    flag: str | None
    value: str | None
    start: int
    end: int


class Operation(NamedTuple):
    route: tuple[str, ...]
    start: int
    items: list[Argument]
    argv: list[str] | None = None


@dataclass
class Contents:
    directory: Path
    values: list[tuple[str, str]] = field(default_factory=list)
    stdin: bytes | None = None

    def add(self, label: str, text: str) -> None:
        self.values.append((label, text))

    def freeze(self, label: str, source: str) -> str:
        if source == "-":
            if self.stdin is None:
                self.stdin = sys.stdin.buffer.read()
            raw: bytes = self.stdin
        else:
            raw = Path(source).read_bytes()
        self.add(label, raw.decode("utf-8"))
        target: Path = self.directory / str(len(self.values))
        target.write_bytes(raw)
        target.chmod(0o600)
        return str(target)


def arguments(args: list[str], value_flags: set[str], start: int = 0) -> Iterator[Argument]:
    """Retain original spans instead of reconstructing unknown native CLI options."""
    index: int = start
    positional: bool = False
    while index < len(args):
        begin: int = index
        arg: str = args[index]
        flag, value = None, arg
        if arg == "--" and not positional:
            positional = True
            flag, value = "--", None
        elif not positional and arg.startswith("-") and arg != "-":
            flag, value = arg, None
            if arg.startswith("--") and "=" in arg:
                flag, value = arg.split("=", 1)
            elif len(arg) > 3 and arg[2] == "=":
                flag, value = arg[:2], arg[3:]
            elif len(arg) > 2 and arg[:2] in value_flags:
                flag, value = arg[:2], arg[2:]
            if flag in value_flags and value is None:
                index += 1
                if index >= len(args):
                    raise Blocked(
                        "Missing command argument value.\n"
                        "Action: Supply the option value and retry."
                    )
                value = args[index]
        index += 1
        yield Argument(flag, value, begin, index)


def expand_short_options(args: list[str], value_flags: set[str]) -> list[str]:
    """Expand boolean clusters without splitting option values or positional text."""
    expanded: list[str] = list(args)
    index: int = 0
    while index < len(expanded):
        item: Argument = next(arguments(expanded, value_flags, index))
        if item.flag == "--":
            break
        flag: str = item.flag or ""
        if flag.startswith("-") and not flag.startswith("--") and len(flag) > 2:
            expanded[index : index + 1] = [flag[:2], "-" + flag[2:]]
            index += 1
        else:
            index = item.end
    return expanded


def command(
    args: list[str], depths: dict[str, int], global_flags: set[str]
) -> tuple[tuple[str, ...], int]:
    route: list[str] = []
    for item in arguments(args, global_flags):
        if item.flag is not None:
            continue
        route.append(item.value)
        depth: int = depths.get(route[0], 0)
        if not depth or len(route) == depth:
            return tuple(route), item.end
    return tuple(route), len(args)
