"""Scan text offline with the pinned Betterleaks executable."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

VERSION: str = Path(__file__).with_name("betterleaks.lock").read_text().splitlines()[0]


class EngineError(Exception):
    """A safe, actionable diagnostic that never includes scanner output."""


def executable(data_home: Path | None = None) -> Path:
    directory: Path = data_home or Path(
        os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))
    )
    return directory / "cli_guard" / "engine" / VERSION / "betterleaks"


def check(text: str, patterns: dict[str, str]) -> tuple[int, str] | None:
    # Explicit config, a private cwd and an empty ignore file prevent project bypasses.
    config: str = "[extend]\nuseDefault = true\n"
    for name, pattern in patterns.items():
        config += (
            "\n[[rules]]\nid = "
            + json.dumps(name)
            + "\nregex = "
            + json.dumps(pattern, ensure_ascii=False)
            + "\n"
        )
    with tempfile.TemporaryDirectory(prefix="cli-guard-engine-") as directory:
        root: Path = Path(directory)
        (root / "rules.toml").write_text(config, encoding="utf-8")
        (root / "ignore").touch()
        env: dict[str, str] = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("BETTERLEAKS_", "GITLEAKS_"))
        }
        args: list[str] = [
            str(executable()),
            "stdin",
            "--config",
            str(root / "rules.toml"),
            "--validation=false",
            "--ignore-gitleaks-allow",
            "--gitleaks-ignore-path",
            str(root / "ignore"),
            "--no-banner",
            "--no-color",
            "--log-level",
            "error",
            "--redact=100",
            "--report-format",
            "json",
            "--report-path",
            "-",
            "--exit-code",
            "23",
        ]
        try:
            result: subprocess.CompletedProcess = subprocess.run(
                args,
                input=text,
                text=True,
                encoding="utf-8",
                capture_output=True,
                cwd=root,
                env=env,
                timeout=3,
            )
        except OSError:
            raise EngineError(
                "Betterleaks is unavailable. Run sh apps/cli-guard/install.sh "
                "with the same --config option, then retry."
            ) from None
        except subprocess.TimeoutExpired:
            raise EngineError(
                "Betterleaks exceeded the 3-second limit. Shorten the content and retry."
            ) from None
    try:
        findings: Any = json.loads(result.stdout)
        if (
            result.returncode not in {0, 23}
            or not isinstance(findings, list)
            or bool(findings) != (result.returncode == 23)
        ):
            raise ValueError("invalid scanner status")
        if not findings:
            return None
        first: Any = findings[0]
        line: Any = first["StartLine"]
        rule: Any = first["RuleID"]
        if (
            type(line) is not int
            or line < 1
            or not isinstance(rule, str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,100}", rule)
        ):
            raise ValueError("invalid finding")
        return line, rule
    except (ValueError, KeyError, TypeError):
        raise EngineError(
            "Betterleaks failed or returned an invalid report. "
            "Check scan.secrets.patterns in config.toml and reinstall if needed."
        ) from None
